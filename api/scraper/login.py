import logging
import pathlib
import pickle
import secrets
import shutil

from fastapi import HTTPException
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, ElementNotInteractableException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.ui import WebDriverWait

from . import common
from .common import delete_session

URL = "https://quest.pecs.uwaterloo.ca/psc/AS/ACADEMIC/SA/c/NUI_FRAMEWORK.PT_LANDINGPAGE.GBL"

DUMMY_URL = "https://quest.pecs.uwaterloo.ca/nonexistent"

PROFILE_PATH = f"{pathlib.Path(__file__).parent.parent}/profiles"


class UserAuthenticationException(Exception):
    token: str

    def __init__(self, message, token):
        super().__init__(message)
        self.token = token


def create_token() -> str:
    """
    Creates a new token for user
    :return: token
    """
    return secrets.token_urlsafe(16)


def dump_cookies(token: str, cookies: dict) -> None:
    """
    Utility function to dump cookies to file in profile path
    :param token: User token
    :param cookies: Dictionary of cookies
    :return: None
    """
    with open(f"{PROFILE_PATH}/{token}/cookieJar.pkl", "wb+") as f:
        pickle.dump(cookies, f)


def load_cookies(token: str) -> None:
    """
    Utility function to load cookies from file
    :param token: User token
    :return: None
    """
    driver = common.driver_list[token]
    try:
        with open(f"{PROFILE_PATH}/{token}/cookieJar.pkl", "rb") as f:
            cookies = pickle.load(f)
    except FileNotFoundError:
        logging.warning("No cookies found for %s", token)
        return
    driver.get(DUMMY_URL)
    for cookie in cookies:
        logging.debug("Adding cookie %s", cookie)
        common.driver_list[token].add_cookie(cookie)


def ini_driver(token: str, remember_me: bool) -> webdriver.Edge:
    """
    Initializes a new driver instance
    :param token: user token
    :param remember_me: if session should be persistent
    :return driver instance
    """
    options = webdriver.EdgeOptions()
    if not remember_me:
        options.add_argument("inprivate")
    else:
        options.add_argument(f"user-data-dir={PROFILE_PATH}/{token}")
    options.add_experimental_option("detach", True)
    # options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    # """
    # options.add_argument("--remote-debugging-port=0")
    # options.binary_location = "/usr/bin/microsoft-edge-stable"
    # s = service.Service(executable_path='api/msedgedriver')"""
    driver = webdriver.Edge(options=options)
    common.driver_list[token] = driver
    driver.set_window_size(1920, 1080)
    logging.info("Driver created for %s", token)

    return driver


def recreate_session(token: str) -> None:
    """
    Recreates session for user
    :param token: token of user
    """
    if token in common.driver_list:
        driver = common.driver_list[token]
    else:
        logging.info("Recreating session for %s", token)
        driver = ini_driver(token, True)

    load_cookies(token)
    driver.get(URL)

    if not common.verify_signed_on(token):
        raise UserAuthenticationException("Session expired, sign in again", token)


def sign_in(user: str, credentials: str, remember_me: bool) -> [str, str]:
    """
    Sign in user and creates new driver instance if new user
    :param user: uWaterloo email
    :param credentials: password
    :param remember_me: if session should be persistent
    :return: [token, duo_auth_code] duo_auth_code may be None if not required
    """
    if user in common.known_users:
        logging.info("User %s already assigned token %s", user, common.known_users[user])
        token = common.known_users[user]
        recreate_session(token)
        return [token, '']

    token = create_token()
    if remember_me:
        common.known_users[user] = token

    driver = ini_driver(token, remember_me)

    # navigate to sign in form
    driver.get(URL)

    try:
        WebDriverWait(driver, timeout=10).until(ec.title_is("Sign In"))
        try:
            logging.info("Signing in as %s", user)
            username = WebDriverWait(driver, timeout=10).until(lambda d: d.find_element(By.ID, 'userNameInput'))
            username.send_keys(user)
            driver.find_element(By.ID, 'nextButton').click()
            password = WebDriverWait(driver, timeout=10).until(lambda d: d.find_element(By.ID, 'passwordInput'))
            password.send_keys(credentials)
            driver.find_element(By.ID, 'submitButton').click()
        except (TimeoutException, ElementNotInteractableException) as e:
            logging.exception("Sign in failed for %s with %e", user, e)
            raise UserAuthenticationException("Sign in failed, check username and password", token)
    except TimeoutException:
        logging.info("Already authenticated, continuing...")

    if driver.title == "Homepage":  # already signed in
        logging.info("DUO Auth passed by cookie")
        return [token, '']
    else:
        WebDriverWait(driver, timeout=10).until(ec.presence_of_element_located((By.CLASS_NAME, "verification-code")))
        duo_auth_code = driver.find_element(By.CLASS_NAME, 'verification-code').text
        logging.info(f"Parsed DUO Auth code: {duo_auth_code}")
        return [token, duo_auth_code]


def duo_auth(token: str, remember_me: bool) -> None:
    """
    Completes duo auth login step
    :param token: User token
    :param remember_me: If user should be remembered
    :return: None
    """
    driver = common.driver_list[token]
    logging.info("DUO Auth required. Waiting for user interaction...")
    try:
        wait = WebDriverWait(driver, timeout=120)
        if remember_me:
            wait.until(ec.element_to_be_clickable((By.ID, "trust-browser-button"))).click()
        else:
            wait.until(ec.element_to_be_clickable((By.ID, "dont-trust-browser-button"))).click()
        # wait until duo auth is passed
        WebDriverWait(driver, timeout=60).until(ec.title_is("Homepage"))
        logging.info("Sign in successful for %s", token)

        dump_cookies(token, driver.get_cookies())
    except TimeoutException:
        logging.error("Duo Auth timed out")
        raise UserAuthenticationException("Duo Auth timed out", token)


def sign_out(token: str) -> str:
    """
    Signs out user, deletes user data and driver instance
    :param token: token to be signed out
    :return: token that was signed out
    """
    logging.info("Signing out user %s", token)
    delete_session(token)
    # delete profile folder
    user_to_delete = next((key for key, value in common.known_users.items() if value == token), None)
    if user_to_delete is not None:
        del common.known_users[user_to_delete]
        shutil.rmtree(f"profiles/{token}")

    return token
