import pathlib
import secrets

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.edge import service
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from . import common

URL = "https://quest.pecs.uwaterloo.ca/psp/SS/?cmd=loginlanguageCd+ENG"


def generate_token():
    return secrets.token_urlsafe(16)


def ini_driver(remember_me):
    options = webdriver.EdgeOptions()
    token = generate_token()
    if not remember_me:
        options.add_argument("inprivate")
    else:
        options.add_argument(f"user-data-dir={pathlib.Path().absolute()}/profiles/{token}")
    options.add_experimental_option("detach", True)
    options.add_argument("--headless")
    options.add_argument("--remote-debugging-port=0")
    options.add_argument("--no-sandbox")
    options.binary_location = "/usr/bin/microsoft-edge-stable"
    s = service.Service(executable_path='api/msedgedriver')
    driver = webdriver.Edge(options=options, service=s)
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
            return 0
    except TimeoutException:
        print("Already authenticated, continuing...")

    if remember_me:
        if driver.title == "Homepage":  # already signed in
            print("DUO Auth passed by cookie")
            return token
        else:  # not yet signed in
            # save cookie
            driver.switch_to.frame("duo_iframe")
            wait = WebDriverWait(driver, timeout=5)

            wait.until(lambda d: d.find_element(By.CLASS_NAME, "btn-cancel")).click()
            wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR,
                                                   "#login-form > div:nth-child(17) > div > label > input[type=checkbox]"))).click()

            print("Waiting for DUO auth")

            driver.find_element(By.CSS_SELECTOR, "#auth_methods > fieldset > div.row-label.push-label > button").click()

            driver.switch_to.default_content()
    # wait until duo auth is passed
    try:
        print("Waiting for user interaction...")
        WebDriverWait(driver, timeout=60).until(EC.title_is("Homepage"))
        return token
    except TimeoutException:
        print("Duo Auth timed out")
        return 0
