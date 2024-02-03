import time

from selenium.common import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
from selenium.webdriver.support.ui import WebDriverWait

from . import common

driver_list = common.driver_list


# all functions require logged-in user


def search_classes(term, subject, number, token):
    driver = driver_list[token]
    common.verify_correct_page("Class Schedule", driver)

    driver.switch_to.frame(
        WebDriverWait(driver, timeout=5).until(lambda d: d.find_element(By.CSS_SELECTOR, "#main_target_win0")))

    driver.find_element(By.CSS_SELECTOR, "#PSTAB > table > tbody > tr > td:nth-child(3) > a").click()
    time.sleep(1)
    Select(driver.find_element(By.CSS_SELECTOR, r"#CLASS_SRCH_WRK2_STRM\$35\$")).select_by_visible_text(term)
    time.sleep(1)
    driver.find_element(By.CSS_SELECTOR, r"#SSR_CLSRCH_WRK_SUBJECT\$0").send_keys(subject)
    time.sleep(1)
    driver.find_element(By.CSS_SELECTOR, r"#SSR_CLSRCH_WRK_CATALOG_NBR\$1").send_keys(number)
    time.sleep(1)
    driver.find_element(By.CSS_SELECTOR, r"#SSR_CLSRCH_WRK_SSR_OPEN_ONLY\$3").click()
    time.sleep(1)

    driver.find_element(By.CSS_SELECTOR, "#CLASS_SRCH_WRK2_SSR_PB_CLASS_SRCH").click()

    try:
        WebDriverWait(driver, timeout=15).until(
            EC.text_to_be_present_in_element((By.ID, "DERIVED_REGFRM1_TITLE1"), "Search Results"))
    except TimeoutException as e:
        if (driver.find_element(
                By.ID, "DERIVED_CLSMSG_ERROR_TEXT").text == "The search returns no results that match the criteria specified."):
            print("No results found")
            return 2
        else:
            print("Search failed {}".format(e))
            return 1

    table = driver.find_element(By.CSS_SELECTOR, r"#ACE_\$ICField48\$0 > tbody")
    num_of_rows = round(len(driver.find_elements(By.CSS_SELECTOR, r"#ACE_\$ICField48\$0 > tbody > tr")) / 2)
    print(f"Found {num_of_rows} sections")

    data = {}

    for i in range(num_of_rows):
        section = table.find_element(By.ID, f"MTG_CLASSNAME\\${i}").text.split("\n")[0].split("-")

        data[f"{section[1]} {section[0]}"] = [
            table.find_element(By.ID, f"MTG_ROOM\\${i}").text,
            table.find_element(By.ID, f"MTG_INSTR\\${i}").text]

    driver.switch_to.default_content()
    return data
