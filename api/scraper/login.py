import pathlib
import secrets
import shutil

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, ElementNotInteractableException
from selenium.webdriver.common.by import By
from selenium.webdriver.edge import service
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from . import common

URL = "https://quest.pecs.uwaterloo.ca/psp/SS/?cmd=loginlanguageCd+ENG"


def generate_token():
    return secrets.token_urlsafe(16)


def ini_driver(remember_me):
    # TODO: Check for existing driver
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
    """
    options.add_argument("--remote-debugging-port=0")
    options.binary_location = "/usr/bin/microsoft-edge-stable"
    s = service.Service(executable_path='api/msedgedriver')"""
    driver = webdriver.Edge(options=options)
    common.driver_list[token] = driver
    driver.set_window_size(1920, 1080)

    return token


def sign_in(user, credentials, remember_me):
    token = ini_driver(remember_me)
    driver = common.driver_list[token]

    # navigate to sign in form
    driver.get(URL)
    driver.find_element(By.LINK_TEXT, "Sign In").click()
    try:
        WebDriverWait(driver, timeout=10).until(EC.title_is("Sign In"))
        try:
            username = WebDriverWait(driver, timeout=10).until(lambda d: d.find_element(By.ID, 'userNameInput'))
            username.send_keys(user)
            driver.find_element(By.ID, 'nextButton').click()
            password = WebDriverWait(driver, timeout=10).until(lambda d: d.find_element(By.ID, 'passwordInput'))
            password.send_keys(credentials)
            driver.find_element(By.ID, 'submitButton').click()
        except TimeoutException as e:  # Sign in failed, password or username incorrect
            print(e)
            sign_out(token)
            return 0
        except ElementNotInteractableException as e:  # Sign in failed, password or username incorrect
            print(e)
            sign_out(token)
            return 0
    except TimeoutException:
        print("Already authenticated, continuing...")

    if driver.title == "Homepage":  # already signed in
        print("DUO Auth passed by cookie")
        return token
    try:
        print("DUO Auth required. Waiting for user interaction...")
        if remember_me:
            wait = WebDriverWait(driver, timeout=120)
            wait.until(EC.element_to_be_clickable((By.ID, "trust-browser-button"))).click()
        else:
            wait = WebDriverWait(driver, timeout=120)
            wait.until(EC.element_to_be_clickable((By.ID, "dont-trust-browser-button"))).click()
        # wait until duo auth is passed
        WebDriverWait(driver, timeout=60).until(EC.title_is("Homepage"))
        return token
    except TimeoutException:
        print("Duo Auth timed out")
        sign_out(token)
        return 0


def sign_out(token):
    driver = common.driver_list[token]
    driver.quit()
    del common.driver_list[token]
    # delete profile folder
    shutil.rmtree(f"profiles/{token}")
    return token
