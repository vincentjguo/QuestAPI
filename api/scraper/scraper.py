import asyncio
import concurrent
import datetime
import logging
import pathlib
import pickle
import sqlite3

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, ElementNotInteractableException, NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.edge.service import Service as EdgeService
from webdriver_manager.microsoft import EdgeChromiumDriverManager

from ..database import db

URL = "https://quest.pecs.uwaterloo.ca/psc/AS/ACADEMIC/SA/c/NUI_FRAMEWORK.PT_LANDINGPAGE.GBL"
DUMMY_URL = "https://quest.pecs.uwaterloo.ca/nonexistent"
PROFILE_PATH = f"{pathlib.Path().cwd()}/profiles"

DUO_AUTH_TIMEOUT = 30


webdriver_executor = concurrent.futures.ThreadPoolExecutor(max_workers=10, thread_name_prefix="webdriver_wait")
edge_service = EdgeService(EdgeChromiumDriverManager().install())


class UserAuthenticationException(Exception):
    def __init__(self, message, token: str):
        super().__init__(message)
        self.token = token


class Scraper:
    driver_list: {str, WebDriver} = {}

    def __init__(self, token: str):
        self.logger = logging.getLogger("scraper[" + token + "]")
        self.token = token
        self.driver: WebDriver = self.__ini_driver()
        self.last_accessed = datetime.datetime.now()

    def __dump_cookies(self, cookies: list[dict]) -> None:
        """
        Utility function to dump cookies to file in profile path
        :param cookies: Dictionary of cookies
        """
        db.save_cookies(self.token, pickle.dumps(cookies))

    def __load_cookies(self) -> None:
        """
        Utility function to load cookies from file
        """
        try:
            cookies = pickle.loads(db.load_cookies(self.token))
        except sqlite3.Error:
            self.logger.warning("No cookies found for %s", self.token)
            return
        self.driver.get(DUMMY_URL)
        for cookie in cookies:
            self.logger.debug("Adding cookie %s", cookie)
            Scraper.driver_list[self.token].add_cookie(cookie)

    def __ini_driver(self) -> WebDriver:
        """
        Initializes a new driver instance
        :return: WebDriver
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
        driver = webdriver.Edge(service=edge_service, options=options)
        Scraper.driver_list[self.token] = driver
        driver.set_window_size(1920, 1080)
        self.logger.info("Driver created for %s", self.token)

        return driver

    def __idle_refresh(self):
        """
        Refreshes idle timer or restarts session if already closed
        """
        self.last_accessed = datetime.datetime.now()

    def verify_signed_on(self) -> bool:
        """
        Verifies if user is signed in
        :return: True if signed in, False if not
        """
        try:
            Scraper.driver_list[self.token].find_element(By.CSS_SELECTOR, "#PT_ACTION_MENU\\$PIMG")
            return True
        except NoSuchElementException:
            self.logger.info("%s not signed in", self.token)
            return False
        except KeyError:
            self.logger.info("No driver found for %s", self.token)
            return False

    def recreate_session(self) -> 'Scraper':
        """
        Recreates session for user. Updates last accessed time
        """
        self.__idle_refresh()
        if self.token in Scraper.driver_list:
            self.driver = Scraper.driver_list[self.token]
        else:
            self.logger.info("Recreating session for %s", self.token)

        self.__load_cookies()
        self.driver.get(URL)

        if not self.verify_signed_on():
            raise UserAuthenticationException("Session expired, sign in again", self.token)

        return self

    async def sign_in(self, user: str, credentials: str) -> str | None:
        """
        Sign in user and creates new driver instance if new user. Updates last accessed time
        :param user: uWaterloo email
        :param credentials: password
        :return: [token, duo_auth_code] duo_auth_code may be None if not required
        """
        self.__idle_refresh()

        # navigate to sign in form
        self.driver.get(URL)

        try:
            await self.wait_for_element(ec.title_is("Sign In"))
            try:
                self.logger.info("Signing in as %s", user)
                username = await self.wait_for_element(lambda d: d.find_element(By.ID, 'userNameInput'))
                username.send_keys(user)
                self.driver.find_element(By.ID, 'nextButton').click()
                password = await self.wait_for_element(lambda d: d.find_element(By.ID, 'passwordInput'))
                password.send_keys(credentials)
                self.driver.find_element(By.ID, 'submitButton').click()
            except (TimeoutException, ElementNotInteractableException) as e:
                self.logger.exception("Sign in failed for %s with %e", user, e)
                raise UserAuthenticationException("Sign in failed, check username and password", self.token)
        except TimeoutException:
            self.logger.info("Already authenticated, continuing...")

        if self.driver.title == "Homepage":  # already signed in
            self.logger.info("DUO Auth passed by cookie")
            self.__dump_cookies(self.driver.get_cookies())
            return None
        else:  # begin duo auth flow
            await self.wait_for_element(ec.presence_of_element_located((By.CLASS_NAME, "verification-code")))
            duo_auth_code = self.driver.find_element(By.CLASS_NAME, 'verification-code').text
            self.logger.info(f"Parsed DUO Auth code: {duo_auth_code}")
            return duo_auth_code

    async def duo_auth(self, remember_me: bool) -> None:
        """
        Completes duo auth login step. Updates last accessed time
        :param remember_me: If user should be remembered
        :raises UserAuthenticationException: if duo auth fails to pass
        """
        self.__idle_refresh()
        self.logger.info("DUO Auth required. Waiting for user interaction...")
        try:
            if remember_me:
                (await self.wait_for_element(ec.element_to_be_clickable((By.ID, "trust-browser-button")),
                                             DUO_AUTH_TIMEOUT)).click()
            else:
                (await self.wait_for_element(ec.element_to_be_clickable((By.ID, "dont-trust-browser-button")),
                                             DUO_AUTH_TIMEOUT)).click()
            # wait until duo auth is passed
            await self.wait_for_element(ec.title_is("Homepage"), timeout=DUO_AUTH_TIMEOUT)
            self.logger.info("Sign in successful for %s", self.token)
            if remember_me:
                self.__dump_cookies(self.driver.get_cookies())
        except TimeoutException:
            self.logger.error("Duo Auth timed out")
            raise UserAuthenticationException("Duo Auth timed out", self.token)

        return

    async def wait_for_element(self, func, timeout=10) -> WebElement:
        """
        Waits for element to be present. Updates last accessed time
        :param func: function to find element
        :param timeout: time to wait
        :return: WebElement to be found
        """
        self.__idle_refresh()
        return await asyncio.get_running_loop().run_in_executor(webdriver_executor,
                                                                WebDriverWait(self.driver, timeout).until, func)

    async def verify_correct_page(self, title: str) -> None:
        """
        Verifies if page is correct, if not navigates to correct page. Updates last accessed time
        :param title: title of page
        :raises TimeoutException | NoSuchElementException: if page cannot be navigated to
        """
        self.__idle_refresh()
        try:
            self.logger.info("Current page: %s", self.driver.title)
            if self.driver.title == title:
                self.logger.info("Already on page, continuing...")
            elif self.driver.title != "Homepage":
                self.logger.info("Navigating to homepage")
                self.driver.get(URL)

            self.logger.info("Navigating to page %s...", title)
            await self.wait_for_element(ec.title_is("Homepage"))
            (await self.wait_for_element(lambda d: d.find_element(By.XPATH, f"//span[.='{title}']"))).click()
        except (TimeoutException, NoSuchElementException) as e:
            self.logger.exception("Could not navigate to page %s, possible sign out for user?", title)
            raise e

    def delete_session(self) -> None:
        """
        Deletes scraper session
        """
        if self.token not in Scraper.driver_list and self.token != '':
            self.logger.debug("No driver found for %s. Ignoring...", self.token)
            return
        self.driver.quit()
        del Scraper.driver_list[self.token]
        self.logger.info("Driver removed for %s", self.token)

    def __del__(self):
        self.delete_session()
        self.logger.info("Scraper object deleted")
