from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

driver_list = {}


def verify_correct_page(title, driver: webdriver):
    if driver.title == title:
        print("Already on page, continuing...")
        return 0
    elif driver.title != "Homepage":
        driver.find_element(By.ID, "PT_WORK_PT_BUTTON_BACK").click()

    print(f"Navigating to page, {title}")
    WebDriverWait(driver, timeout=10).until(EC.title_is("Homepage"))
    WebDriverWait(driver, timeout=10).until(lambda d: d.find_element(By.XPATH, f"//span[.='{title}']")).click()
    return 1