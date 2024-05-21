import asyncio
import logging
from asyncio import CancelledError

import websockets

from api.scraper import login, common
from api.websocket import connect

LOG_LEVEL = logging.DEBUG


async def websocket():
    try:
        async with websockets.serve(connect, "localhost", 8765):
            await asyncio.Future()  # run forever
    except (KeyboardInterrupt, CancelledError) as e:
        logging.info("Shutting down server...")
        for user in common.known_users.values():
            login.sign_out(user)


if __name__ == "__main__":
    logging.basicConfig(
        format='[%(asctime)s] %(name)s %(taskName)s %(threadName)s {%(filename)s:%(lineno)d} %(levelname)s - %(message)s',
        level=LOG_LEVEL)
    asyncio.run(websocket())
