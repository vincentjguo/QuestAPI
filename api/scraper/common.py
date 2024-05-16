import logging

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

driver_list = {}
known_users = {}


def verify_signed_on(token: str) -> bool:
    """
    Verifies if user is signed in
    :param token: token of user
    :return: true if signed in, false if not
    """
    try:
        driver_list[token].find_element(By.CSS_SELECTOR, "#PT_ACTION_MENU\\$PIMG")
        return True
    except NoSuchElementException:
        logging.info("%s not signed in", token)
        return False


def verify_correct_page(title: str, driver: webdriver) -> None:
    """
    Verifies if page is correct, if not navigates to correct page
    :param title: title of page
    :param driver: driver instance
    """
    try:
        logging.info("Current page: %s", driver.title)
        if driver.title == title:
            logging.info("Already on page, continuing...")
        elif driver.title != "Homepage":
            logging.info("Navigating to homepage")
            driver.find_element(By.ID, "PT_WORK_PT_BUTTON_BACK").click()

        logging.info("Navigating to page %s...", title)
        WebDriverWait(driver, timeout=10).until(EC.title_is("Homepage"))
        WebDriverWait(driver, timeout=10).until(lambda d: d.find_element(By.XPATH, f"//span[.='{title}']")).click()
    except (TimeoutException, NoSuchElementException):
        logging.exception("Could not navigate to page %s, possible sign out for user %s?", title, driver.title)


def delete_session(token: str) -> None:
    """
    Deletes session
    :param token: token of user
    """
    if token not in driver_list and token is not None:
        logging.debug("No driver found for %s. Ignoring...", token)
        return
    driver_list[token].quit()
    del driver_list[token]
    logging.info("Driver removed for %s", token)
