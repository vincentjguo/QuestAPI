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
SSL_CONTEXT = None


async def websocket():
    try:
        async with websockets.serve(connect, "localhost", 4444, ssl=SSL_CONTEXT):
            await asyncio.Future()  # run forever
    except (KeyboardInterrupt, CancelledError) as e:
        logging.info("Shutting down server...")
        tokens = common.known_users.values()
        for user in tokens:
            login.sign_out(user)


def load_cert(cert_path: str, key_path: str):
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    try:
        ssl_context.load_cert_chain(cert_path, key_path)
    except FileNotFoundError as e:
        logging.error("Certificate or key file not found: %s", e)
        exit(1)


if __name__ == "__main__":
    cert_path = os.getenv('CERT_PATH', '')
    key_path = os.getenv('KEY_PATH', '')
    debug = os.getenv('DEBUG', 'False') == 'True'

    if debug:
        LOG_LEVEL = logging.DEBUG

    logging.basicConfig(
        format='[%(asctime)s] %(name)s %(taskName)s %(threadName)s {%(filename)s:%(lineno)d} %(levelname)s - %('
               'message)s',
        level=LOG_LEVEL)
    if cert_path != "" and key_path != "":
        logging.info("Picked up certificate path %s and key %s", cert_path, key_path)
        load_cert(cert_path, key_path)
    asyncio.run(websocket())
