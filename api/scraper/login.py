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

URL = "https://quest.pecs.uwaterloo.ca/psp/SS/?cmd=loginlanguageCd+ENG"
known_users = {}


def generate_token():
    return secrets.token_urlsafe(16)


def ini_driver(remember_me: bool) -> str:
    """
    Initializes a new driver instance
    :param remember_me: if session should be persistent
    :return: token of new driver instance
    """
    options = webdriver.EdgeOptions()
    token = generate_token()
    if not remember_me:
        options.add_argument("inprivate")
    else:
        options.add_argument(f"user-data-dir={pathlib.Path().absolute()}/profiles/{token}")
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

    return token


def sign_in(user: str, credentials: str, remember_me: bool) -> str:
    """
    Sign in user and creates new driver instance if new user
    :param user: uwaterloo email
    :param credentials: password
    :param remember_me: if session should be persistent
    :return: token of user
    """

    token: str
    if user in known_users:
        logging.warning("User %s already assigned token %s", user, known_users[user])
        token = known_users[user]
    else:
        token = ini_driver(remember_me)

    driver = common.driver_list[token]
    # navigate to sign in form
    driver.get(URL)
    driver.find_element(By.LINK_TEXT, "Sign In").click()
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
        except TimeoutException | ElementNotInteractableException:  # Sign in failed, password or username incorrect
            logging.exception("Sign in failed for %s", user)
            sign_out(token)
            raise HTTPException(status_code=401, detail="Sign in failed, check username and password")
    except TimeoutException:
        logging.info("Already authenticated, continuing...")

    if driver.title == "Homepage":  # already signed in
        logging.info("DUO Auth passed by cookie")
        return token
    try:
        logging.info("DUO Auth required. Waiting for user interaction...")
        if remember_me:
            wait = WebDriverWait(driver, timeout=120)
            wait.until(EC.element_to_be_clickable((By.ID, "trust-browser-button"))).click()
        else:
            wait = WebDriverWait(driver, timeout=120)
            wait.until(EC.element_to_be_clickable((By.ID, "dont-trust-browser-button"))).click()
        # wait until duo auth is passed
        WebDriverWait(driver, timeout=60).until(EC.title_is("Homepage"))
        logging.info("Sign in successful for %s", user)
        return token
    except TimeoutException:
        logging.error("Duo Auth timed out")
        sign_out(token)
        raise HTTPException(status_code=401, detail="Duo Auth timed out")


def sign_out(token: str) -> str:
    """
    Signs out user and deletes driver instance
    :param token: token to be signed out
    :return: token that was signed out
    """
    logging.info("Signing out user %s", token)
    driver = common.driver_list[token]
    driver.quit()
    del common.driver_list[token]
    # delete profile folder
    shutil.rmtree(f"profiles/{token}")
    return token
