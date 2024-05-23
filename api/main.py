import argparse
import asyncio
import logging
import os
import ssl
from asyncio import CancelledError

import websockets

from .scraper import login, common
from .websocket import connect

LOG_LEVEL = logging.INFO


async def websocket():
    try:
        async with websockets.serve(connect, "localhost", 4444):
            await asyncio.Future()  # run forever
    except (KeyboardInterrupt, CancelledError) as e:
        logging.info("Shutting down server...")
        tokens = common.known_users.values()
        for user in tokens:
            login.sign_out(user)


if __name__ == "__main__":
    debug = os.getenv('DEBUG', 'False') == 'True'

    if debug:
        LOG_LEVEL = logging.DEBUG

    logging.basicConfig(
        format='[%(asctime)s] %(name)s %(taskName)s %(threadName)s {%(filename)s:%(lineno)d} %(levelname)s - %('
               'message)s',
        level=LOG_LEVEL)
    asyncio.run(websocket())
