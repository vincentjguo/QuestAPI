import logging

from selenium.common import TimeoutException, NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.ui import Select

from api.database.models.course_info_model import Course, Section
from ..exceptions import SessionException
from .scraper import Scraper


class ScheduleException(SessionException):
    def __init__(self, message):
        super().__init__(message)


async def search_classes(scraper: Scraper, term: str, subject: str, number: str) -> Course:
    """
    Searches for classes
    :param scraper:
    :param term:
    :param subject:
    :param number:
    :return:
    """
    course = Course(term, subject, number)

    driver = scraper.driver
    await scraper.verify_correct_page("Class Schedule")

    logging.info("Searching for %s %s %s", term, subject, number)
    try:
        driver.switch_to.frame(
            await scraper.wait_for_element(lambda d: d.find_element(By.CSS_SELECTOR, "#main_target_win0")))

        driver.find_element(By.CSS_SELECTOR, "#PSTAB > table > tbody > tr > td:nth-child(3) > a").click()
        Select(driver.find_element(By.CSS_SELECTOR, r"#CLASS_SRCH_WRK2_STRM\$35\$")).select_by_value(term)
        driver.find_element(By.CSS_SELECTOR, r"#SSR_CLSRCH_WRK_SUBJECT\$0").send_keys(subject)
        driver.find_element(By.CSS_SELECTOR, r"#SSR_CLSRCH_WRK_CATALOG_NBR\$1").send_keys(number)
        driver.find_element(By.CSS_SELECTOR, r"#SSR_CLSRCH_WRK_SSR_OPEN_ONLY\$3").click()

        driver.find_element(By.CSS_SELECTOR, "#CLASS_SRCH_WRK2_SSR_PB_CLASS_SRCH").click()
        await scraper.wait_for_element(
                               ec.text_to_be_present_in_element((By.ID, "DERIVED_REGFRM1_TITLE1"),
                                                                "Search Results"))
    except (TimeoutException, NoSuchElementException) as e:
        logging.error("Search failed for %s %s %s", term, subject, number)
        logging.debug(e)
        raise ScheduleException("No results found")

    table = driver.find_element(By.CSS_SELECTOR, r"#ACE_\$ICField48\$0 > tbody")
    num_of_rows = round(len(driver.find_elements(By.CSS_SELECTOR, r"#ACE_\$ICField48\$0 > tbody > tr")) / 2)
    logging.info("Found %s sections", num_of_rows)

    for i in range(num_of_rows):
        section = table.find_element(By.ID, f"MTG_CLASSNAME\\${i}").text.split("\n")[0].split("-")
        course.add_section(
            Section(section[1], section[0], table.find_element(By.ID, f"MTG_ROOM\\${i}").text,
                    table.find_element(By.ID, f"MTG_INSTR\\${i}").text))

    logging.info("Aggregated data: %s", course)

    driver.switch_to.default_content()
    return course
