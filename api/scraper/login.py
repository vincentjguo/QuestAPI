import logging
import pathlib
import secrets
import shutil

from fastapi import HTTPException
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, ElementNotInteractableException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from . import common
from .common import delete_session

URL = "https://quest.pecs.uwaterloo.ca/psc/AS/ACADEMIC/SA/c/NUI_FRAMEWORK.PT_LANDINGPAGE.GBL"


class UserAuthenticationException(Exception):
    def __init__(self, message):
        super().__init__(message)


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
        options.add_argument(f"user-data-dir={pathlib.Path(__file__).parent}/../profiles/{token}")
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

    driver.get(URL)

    if not common.verify_signed_on(token):
        raise UserAuthenticationException("Session expired, sign in again")


def sign_in(user: str, credentials: str, remember_me: bool, token: str) -> str:
    """
    Sign in user and creates new driver instance if new user
    :param token: newly generated token
    :param user: uwaterloo email
    :param credentials: password
    :param remember_me: if session should be persistent
    :return: duo auth code if required, '' if not
    """

    if user in common.known_users:
        logging.info("User %s already assigned token %s", user, common.known_users[user])
        token = common.known_users[user]
    elif remember_me:
        common.known_users[user] = token

    if token in common.driver_list:
        driver = common.driver_list[token]
    else:
        driver = ini_driver(token, remember_me)
    # navigate to sign in form
    driver.get(URL)

    if common.verify_signed_on(token):  # user already signed in
        return ''

    try:
        WebDriverWait(driver, timeout=10).until(EC.title_is("Sign In"))
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
            sign_out(token)
            raise UserAuthenticationException("Sign in failed, check username and password")
    except TimeoutException:
        logging.info("Already authenticated, continuing...")

    if driver.title == "Homepage":  # already signed in
        logging.info("DUO Auth passed by cookie")
        return ''
    else:
        WebDriverWait(driver, timeout=10).until(EC.presence_of_element_located((By.CLASS_NAME, "verification-code")))
        duo_auth_code = driver.find_element(By.CLASS_NAME, 'verification-code').text
        logging.info(f"Parsed DUO Auth code: {duo_auth_code}")
        return duo_auth_code


def duo_auth(token: str, remember_me) -> str:
    driver = common.driver_list[token]
    logging.info("DUO Auth required. Waiting for user interaction...")
    try:
        wait = WebDriverWait(driver, timeout=120)
        if remember_me:
            wait.until(EC.element_to_be_clickable((By.ID, "trust-browser-button"))).click()
        else:
            wait.until(EC.element_to_be_clickable((By.ID, "dont-trust-browser-button"))).click()
        # wait until duo auth is passed
        WebDriverWait(driver, timeout=60).until(EC.title_is("Homepage"))
        logging.info("Sign in successful for %s", token)
        return token
    except TimeoutException:
        logging.error("Duo Auth timed out")
        sign_out(token)
        raise UserAuthenticationException("Duo Auth timed out")


def sign_out(token: str) -> str:
    """
    Signs out user, deletes user data and driver instance
    :param token: token to be signed out
    :return: token that was signed out
    """
    logging.info("Signing out user %s", token)
    delete_session(token, True)
    # delete profile folder
    shutil.rmtree(f"profiles/{token}")
    return token
