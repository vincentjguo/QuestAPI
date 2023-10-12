import hashlib

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

driver_list = {}


def verify_signed_on(driver):
    try:
        driver.find_element(By.CSS_SELECTOR, "#PT_ACTION_MENU\\$PIMG")
        return 0
    except NoSuchElementException:
        print("Not signed on")
        return 1


def verify_correct_page(title, driver: webdriver):
    try:
        if driver.title == title:
            print("Already on page, continuing...")
            return 0
        elif driver.title != "Homepage":
            driver.find_element(By.ID, "PT_WORK_PT_BUTTON_BACK").click()

        print(f"Navigating to page, {title}")
        WebDriverWait(driver, timeout=10).until(EC.title_is("Homepage"))
        WebDriverWait(driver, timeout=10).until(lambda d: d.find_element(By.XPATH, f"//span[.='{title}']")).click()
        return 0
    except (TimeoutException, NoSuchElementException):
        print("Could not navigate page, possible sign out?")
        return 1
