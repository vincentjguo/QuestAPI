import asyncio
import concurrent.futures
import logging

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.ui import WebDriverWait

driver_list: {str, WebDriver} = {}
# {username : token}
known_users = {}
webdriver_executor = concurrent.futures.ThreadPoolExecutor(max_workers=10, thread_name_prefix="webdriver_wait")


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
    except KeyError:
        logging.info("No driver found for %s", token)
        return False


async def verify_correct_page(title: str, driver: webdriver) -> None:
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
        await wait_for_element(driver, ec.title_is("Homepage"))
        (await wait_for_element(driver, lambda d: d.find_element(By.XPATH, f"//span[.='{title}']"))).click()
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


async def wait_for_element(driver, func, timeout=10) -> WebElement:
    """
    Waits for element to be present
    :param driver: driver instance
    :param func: function to find element
    :param timeout: time to wait
    :return: WebElement
    """

    return await asyncio.get_running_loop().run_in_executor(webdriver_executor,
                                                            WebDriverWait(driver, timeout).until, func)
