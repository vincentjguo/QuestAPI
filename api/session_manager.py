import asyncio
import datetime
import logging
import secrets
from contextlib import ContextDecorator

import selenium.common.exceptions
import websockets

from api.database import db
from api.database.models.course_info_model import Course
from api.scraper import schedule
from api.scraper.schedule import ScheduleException
from api.scraper.scraper import Scraper, UserAuthenticationException

BPM = 1
prune_interval = 300

# {username : token}
known_users: {str, str} = db.load_users()


class SessionException(Exception):
    def __init__(self, message):
        super().__init__(message)


class SessionManager(ContextDecorator):

    def __init__(self, token=secrets.token_urlsafe(16)):
        self.heartbeat = None
        self.token = token
        self.scraper = None
        self.logger = logging.getLogger("session_manager[" + token + "]")
        self.active = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # TODO: Fix this for websocket close when user is still active on frontend
        if self.token not in known_users.values():  # if user is not remembered sign out everytime
            self.handle_sign_out()
        else:
            self.remove_scraper()
        return False

    def __str__(self):
        return self.token

    def __repr__(self):
        return self.token

    async def __heartbeat(self) -> None:
        """
        Heartbeat task to check if the session is still active
        :raises websockets.exceptions.SecurityError: session is inactive
        """
        self.logger.debug("Starting heartbeat task")
        try:
            while True:
                await asyncio.sleep(BPM * 60)
                self.logger.debug("Checking pulse for session")

                if self.scraper is None:
                    self.logger.debug("Scraper not initialized. Ending heartbeat task")
                    return

                if self.scraper.last_accessed < datetime.datetime.now() - datetime.timedelta(seconds=prune_interval):
                    self.logger.debug("Scraper inactive for too long. Entering idle state...")
                    self.remove_scraper()
                    return

                # if self.scraper.verify_signed_on():
                #     self.logger.debug("Pulse check passed for this session")
                # else:
                #     self.logger.warning("Pulse check failed for this session")
                #     raise websockets.exceptions.SecurityError("Dead session. Reauthenticate!")
        except asyncio.CancelledError:
            self.logger.debug("Heartbeat task cancelled")
            return

    def set_token(self, token: str) -> None:
        self.token = token
        self.logger = logging.getLogger("session_manager[" + token + "]")
        self.logger.info("Token set to %s", token)

    async def wake_scraper(self) -> None:
        if self.active:
            self.logger.debug("Scraper already active")
            return

        self.logger.info("Waking up scraper...")
        self.create_scraper()
        try:
            self.scraper.recreate_session()
        except UserAuthenticationException as e:
            self.handle_sign_out()
            raise websockets.exceptions.SecurityError(e)

    def create_scraper(self) -> None:
        """
        Creates a new scraper instance and starts heartbeat task
        :raises SessionException: scraper is already active
        """
        if self.active:
            self.logger.warning("Scraper already active")
            raise SessionException("Scraper already active")

        self.scraper = Scraper(self.token)
        self.active = True
        self.heartbeat = asyncio.create_task(self.__heartbeat(), name="heartbeat-" + self.token)

    async def reconnect_user(self) -> str:
        """
        Reconnects a user to an existing session using previously set token
        :return: the existing token used to reconnect
        :raises websockets.exceptions.SecurityError: invalid token
        """
        if self.token not in known_users.values():
            self.logger.error("Unauthorized token %s", self.token)
            raise websockets.exceptions.SecurityError("Invalid token")

        self.logger.info(f"Session created for {self.token}")
        return self.token

    async def create_user(self, user: str, credentials: str, remember_me: bool, callback) -> str:
        """
        Creates a new session for a user with the given credentials
        Callback is for duo auth prompts
        :return: the new token used to create the session
        :raises websockets.exceptions.SecurityError:  credentials invalid
        """

        try:
            if user in known_users:
                self.logger.info("User %s already assigned token %s", user, known_users[user])
                self.token = known_users[user]
                return await self.reconnect_user()

            self.create_scraper()

            duo_auth_code = await self.scraper.sign_in(user, credentials)
            if duo_auth_code is not None:
                self.logger.info("Duo auth code required")
                await callback(duo_auth_code)
                await self.scraper.duo_auth(remember_me)

            if remember_me:
                known_users[user] = self.token
                db.save_user(self.token, user)

            return self.token
        except UserAuthenticationException as e:
            self.handle_sign_out()
            raise websockets.exceptions.SecurityError(e)

    async def handle_search_classes(self, term: str, subject: str, class_number: str) -> dict:
        """
        Handles search requests for classes
        :param term: term code
        :param subject: subject name
        :param class_number: class number
        :raises SessionException: on search failure
        """
        self.logger.info("Received search request for %s %s %s", term, subject, class_number)
        try:
            result = db.get_course_info(term, subject, class_number)
            self.logger.info("Database result: %s", result)
            if result is None:
                self.logger.info("Course info not found in database. Searching...")
                await self.wake_scraper()

                result = await schedule.search_classes(self.scraper, term, subject, class_number)
                db.upsert_course_info(term, result)
        except selenium.common.WebDriverException as e:  # silently log error and continue
            self.logger.exception(e)
            raise SessionException("Unexpected Error: Could not search classes")
        except ScheduleException as e:
            self.logger.warning(e)
            db.upsert_course_info(term, Course(term, subject, class_number))  # set as no results found
            raise SessionException("No results found")
        return result.get_sections()

    def handle_sign_out(self) -> None:
        """
        Signs out the current user and removes from known_users
        """
        self.logger.info("Signing out current user")
        user_to_delete = next((key for key, value in known_users.items() if value == self.token),
                              None)
        if user_to_delete is not None:
            del known_users[user_to_delete]

        db.remove_user(self.token)
        if self.active:
            self.remove_scraper()
        self.active = False

    def remove_scraper(self) -> None:
        """
        Removes the active scraper if it exists and ends the heartbeat task
        """
        if self.active:
            del self.scraper
            self.active = False
            self.heartbeat.cancel()
        else:
            self.logger.info("No active scraper to remove")
