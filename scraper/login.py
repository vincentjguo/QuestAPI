import pathlib

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from . import common
import pickle

URL = "https://quest.pecs.uwaterloo.ca/psp/SS/?cmd=loginlanguageCd+ENG"


def ini_driver(user, remember_me):
    options = webdriver.EdgeOptions()
    if not remember_me:
        options.add_argument("inprivate")
    else:
        options.add_argument(f"user-data-dir={pathlib.Path().absolute()}/profiles/{user.split('@')[0]}")
    options.add_experimental_option("detach", True)
    driver = webdriver.Edge(options=options)
    common.driver_list[user] = driver

    return driver


def sign_in(user, credentials, remember_me):
    driver = ini_driver(user, remember_me)

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
        except TimeoutException as e:
            print(e)
            return 1
    except TimeoutException as e:
        print("Already authenticated")

    if remember_me:
        try:
            WebDriverWait(driver, timeout=10).until(EC.title_contains("Homepage"))
            print("DUO Auth passed by cookie")
        except TimeoutException as e:
            # save cookie
            driver.switch_to.frame("duo_iframe")
            wait = WebDriverWait(driver, timeout=10)
            wait.until(lambda d: d.find_element(By.CSS_SELECTOR, "#messages-view > div > div > div > button")).click()

            wait.until(EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "#login-form > div:nth-child(17) > div > label > input[type=checkbox]"))).click()

            driver.find_element(By.CSS_SELECTOR, "#auth_methods > fieldset > div.row-label.push-label > button").click()

            driver.switch_to.default_content()
    else:
        # wait until duo auth is passed
        try:
            WebDriverWait(driver, timeout=60).until(EC.title_is("Homepage"))
            print("Waiting for user interaction...")
        except TimeoutException as e:
            print("Duo Auth timed out")
            return 2
