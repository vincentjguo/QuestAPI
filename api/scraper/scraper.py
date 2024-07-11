import asyncio
import concurrent
import datetime
import logging
import pathlib
import pickle

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, ElementNotInteractableException, NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.wait import WebDriverWait

from . import common
from ..database import db
from ..token_manager import TokenManager

URL = "https://quest.pecs.uwaterloo.ca/psc/AS/ACADEMIC/SA/c/NUI_FRAMEWORK.PT_LANDINGPAGE.GBL"
DUMMY_URL = "https://quest.pecs.uwaterloo.ca/nonexistent"
PROFILE_PATH = f"{pathlib.Path().cwd()}/profiles"

DUO_AUTH_TIMEOUT = 60

logger = logging.getLogger(__name__)


class UserAuthenticationException(Exception):
    def __init__(self, message, token: TokenManager):
        super().__init__(message)
        self.token = token


class Scraper:
    driver_list: {str, WebDriver} = {}
    last_accessed: {'Scraper', datetime.datetime} = {}

    def __init__(self, token: TokenManager):
        self.token = token
        self.driver: WebDriver = self.__ini_driver()
        self.active = True

    def __dump_cookies(self, cookies: list[dict]) -> None:
        """
        Utility function to dump cookies to file in profile path
        :param cookies: Dictionary of cookies
        :return: None
        """
        db.save_cookies(self.token.get_token(), pickle.dumps(cookies))

    def __load_cookies(self) -> None:
        """
        Utility function to load cookies from file
        :return: None
        """
        try:
            cookies = pickle.loads(db.load_cookies(self.token.get_token()))
        except FileNotFoundError:
            logger.warning("No cookies found for %s", self.token.get_token())
            return
        self.driver.get(DUMMY_URL)
        for cookie in cookies:
            logger.debug("Adding cookie %s", cookie)
            common.driver_list[self.token.get_token()].add_cookie(cookie)

    def __ini_driver(self) -> WebDriver:
        """
        Initializes a new driver instance
        :return driver instance
        """
        options = webdriver.EdgeOptions()
        # if not remember_me:
        #     options.add_argument("inprivate")
        # else:
        #     options.add_argument(f"user-data-dir={PROFILE_PATH}/{self.token.get_token()}")
        options.add_experimental_option("detach", True)
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        # options.add_argument("--remote-debugging-port=0")
        # options.binary_location = "/usr/bin/microsoft-edge-stable"
        # s = service.Service(executable_path='api/msedgedriver')
        driver = WebDriver(options=options)
        self.driver_list[self.token.get_token()] = driver
        driver.set_window_size(1920, 1080)
        logger.info("Driver created for %s", self.token)

        return driver

    def __idle_refresh(self):
        """
        Refreshes idle timer or restarts session if already closed
        """
        Scraper.last_accessed[self] = datetime.datetime.now()

        if not self.active:
            self.recreate_session()
            self.active = True

    def verify_signed_on(self) -> bool:
        """
        Verifies if user is signed in
        :return: true if signed in, false if not
        """
        try:
            self.driver_list[self.token.get_token()].find_element(By.CSS_SELECTOR, "#PT_ACTION_MENU\\$PIMG")
            return True
        except NoSuchElementException:
            logger.info("%s not signed in", self.token)
            return False
        except KeyError:
            logger.info("No driver found for %s", self.token)
            return False

    def recreate_session(self) -> 'Scraper':
        """
        Recreates session for user. Updates last accessed time
        """
        self.__idle_refresh()
        if self.token in self.driver_list:
            self.driver = self.driver_list[self.token]
        else:
            logger.info("Recreating session for %s", self.token)

        self.__load_cookies()
        self.driver.get(URL)

        if not self.verify_signed_on():
            raise UserAuthenticationException("Session expired, sign in again", self.token)

        return self

    async def sign_in(self, user: str, credentials: str, remember_me: bool) -> str | None:
        """
        Sign in user and creates new driver instance if new user. Updates last accessed time
        :param user: uWaterloo email
        :param credentials: password
        :param remember_me: if session should be persistent
        :return: [token, duo_auth_code] duo_auth_code may be None if not required
        """
        self.__idle_refresh()
        # TODO: keep known_users in common?
        if user in common.known_users:
            logger.info("User %s already assigned token %s", user, common.known_users[user])
            self.token.create_from_existing_user(user)
            self.recreate_session()
            return None

        if remember_me:
            common.known_users[user] = self.token.get_token()

        # navigate to sign in form
        self.driver.get(URL)

        try:
            await self.wait_for_element(ec.title_is("Sign In"))
            try:
                logger.info("Signing in as %s", user)
                username = await self.wait_for_element(lambda d: d.find_element(By.ID, 'userNameInput'))
                username.send_keys(user)
                self.driver.find_element(By.ID, 'nextButton').click()
                password = await self.wait_for_element(lambda d: d.find_element(By.ID, 'passwordInput'))
                password.send_keys(credentials)
                self.driver.find_element(By.ID, 'submitButton').click()
            except (TimeoutException, ElementNotInteractableException) as e:
                logger.exception("Sign in failed for %s with %e", user, e)
                raise UserAuthenticationException("Sign in failed, check username and password", self.token)
        except TimeoutException:
            logger.info("Already authenticated, continuing...")

        if self.driver.title == "Homepage":  # already signed in
            logger.info("DUO Auth passed by cookie")
            self.__dump_cookies(self.driver.get_cookies())
            return None
        else:  # begin duo auth flow
            await self.wait_for_element(ec.presence_of_element_located((By.CLASS_NAME, "verification-code")))
            duo_auth_code = self.driver.find_element(By.CLASS_NAME, 'verification-code').text
            logger.info(f"Parsed DUO Auth code: {duo_auth_code}")
            return duo_auth_code

    async def duo_auth(self, remember_me: bool) -> 'Scraper':
        """
        Completes duo auth login step. Updates last accessed time
        :param remember_me: If user should be remembered
        :return: None
        """
        self.__idle_refresh()
        logger.info("DUO Auth required. Waiting for user interaction...")
        try:
            if remember_me:
                (await self.wait_for_element(ec.element_to_be_clickable((By.ID, "trust-browser-button")),
                                             DUO_AUTH_TIMEOUT)).click()
            else:
                (await self.wait_for_element(ec.element_to_be_clickable((By.ID, "dont-trust-browser-button")),
                                             DUO_AUTH_TIMEOUT)).click()
            # wait until duo auth is passed
            await self.wait_for_element(ec.title_is("Homepage"), timeout=60)
            logger.info("Sign in successful for %s", self.token.get_token())
            if remember_me:
                self.__dump_cookies(self.driver.get_cookies())
        except TimeoutException:
            logger.error("Duo Auth timed out")
            raise UserAuthenticationException("Duo Auth timed out", self.token)

        return self

    def sign_out(self) -> str:
        """
        Signs out user, deletes user data and driver instance
        :return: token that was signed out
        """
        logger.info("Signing out user %s", self.token)
        self.delete_session()
        # delete profile folder
        user_to_delete = next((key for key, value in common.known_users.items() if value == self.token.get_token()),
                              None)
        if user_to_delete is not None:
            del common.known_users[user_to_delete]
            db.remove_cookies(self.token.get_token())

        return self.token.get_token()

    async def wait_for_element(self, func, timeout=10) -> WebElement:
        """
        Waits for element to be present. Updates last accessed time
        :param func: function to find element
        :param timeout: time to wait
        :return: WebElement
        """
        self.__idle_refresh()
        webdriver_executor = concurrent.futures.ThreadPoolExecutor(max_workers=10, thread_name_prefix="webdriver_wait")
        return await asyncio.get_running_loop().run_in_executor(webdriver_executor,
                                                                WebDriverWait(self.driver, timeout).until, func)

    async def verify_correct_page(self, title: str) -> None:
        """
        Verifies if page is correct, if not navigates to correct page. Updates last accessed time
        :param title: title of page
        """
        self.__idle_refresh()
        try:
            logger.info("Current page: %s", self.driver.title)
            if self.driver.title == title:
                logger.info("Already on page, continuing...")
            elif self.driver.title != "Homepage":
                logger.info("Navigating to homepage")
                self.driver.get(URL)

            logger.info("Navigating to page %s...", title)
            await self.wait_for_element(ec.title_is("Homepage"))
            (await self.wait_for_element(lambda d: d.find_element(By.XPATH, f"//span[.='{title}']"))).click()
        except (TimeoutException, NoSuchElementException):
            logger.exception("Could not navigate to page %s, possible sign out for user?", title)

    async def delete_session(self) -> None:
        """
        Deletes session
        """
        if self.token.get_token() not in self.driver_list and self.token.get_token() != '':
            logger.debug("No driver found for %s. Ignoring...", self.token)
            return
        self.driver_list[self.token.get_token()].quit()
        del self.driver_list[self.token.get_token()]
        logger.info("Driver removed for %s", self.token)

