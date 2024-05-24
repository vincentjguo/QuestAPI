import asyncio
import logging
import os
from asyncio import CancelledError

import websockets

from .scraper import login, common
from .websocket import connect

LOG_LEVEL = logging.INFO


async def websocket():
    try:
        async with websockets.serve(connect, "0.0.0.0", 4444):
            await asyncio.Future()  # run forever
    except (KeyboardInterrupt, CancelledError):
        logging.info("Shutting down server...")
        tokens = common.known_users.values()
        for token in tokens:
            login.delete_session(token)


if __name__ == "__main__":
    debug = os.getenv('DEBUG', 'False') == 'True'

    if debug:
        LOG_LEVEL = logging.DEBUG

    logging.basicConfig(
        format='[%(asctime)s] %(name)s %(taskName)s %(threadName)s {%(filename)s:%(lineno)d} %(levelname)s - %('
               'message)s',
        level=LOG_LEVEL)
    asyncio.run(websocket())
