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
known_users: {str, str} = {}

webdriver_executor = concurrent.futures.ThreadPoolExecutor(max_workers=10, thread_name_prefix="webdriver_wait")












