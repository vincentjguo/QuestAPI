import asyncio
import logging
import os
import sys
from asyncio import CancelledError

import websockets

from .websocket import connect

LOG_LEVEL = logging.INFO


async def websocket():
    try:
        async with websockets.serve(connect, "0.0.0.0", 4444):
            await asyncio.Future()  # run forever
    except (KeyboardInterrupt, CancelledError):
        logging.info("Shutting down server...")


class CustomFormatter(logging.Formatter):
    grey = "\x1b[37m"
    yellow = "\x1b[33;20m"
    red = "\x1b[31;20m"
    bold_red = "\x1b[31;1m"
    light_blue = "\x1b[1;36m"
    green = "\x1b[32m"
    reset = "\x1b[0m"

    info_format = f"{grey}[%(asctime)s]{reset} {light_blue}%(name)s{reset} {grey}%(taskName)s{reset} {{%(filename)s:%(lineno)d}}"
    msg_format = "%(levelname)s - %(message)s"

    FORMATS = {
        logging.DEBUG: grey + msg_format + reset,
        logging.INFO: green + msg_format + reset,
        logging.WARNING: yellow + msg_format + reset,
        logging.ERROR: red + msg_format + reset,
        logging.CRITICAL: bold_red + msg_format + reset
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(f"{self.info_format} {log_fmt}")
        return formatter.format(record)


if __name__ == "__main__":
    debug = os.getenv('DEBUG', 'False') == 'True'

    if debug:
        LOG_LEVEL = logging.DEBUG

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(CustomFormatter())

    logger = logging.getLogger()
    logger.addHandler(handler)
    logger.setLevel(LOG_LEVEL)

    asyncio.run(websocket())
