import logging

import websockets.exceptions
from websockets import exceptions

import api.main
from api import main


# @main.exception_handler(Exception)
# async def exception_callback(exc: Exception):
#     logging.exception(exc)
#     raise websockets.exceptions.WebSocketException("Internal server error")
