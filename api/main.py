import json
import logging
import secrets
from enum import IntEnum
import asyncio

import selenium.common
import websockets

from api.scraper import login, schedule, common

BPM = 1
WEBSOCKET_TIMEOUT = 3


class WebsocketResponseCode(IntEnum):
    """
    Enum for websocket response codes

    CRITICAL: Connection cannot continue, will be shutdown

    ERROR: Error occurred, connection will continue

    STATUS: Status message, process not finished

    SUCCESS: Successful operation, ready for next query

    PARTIAL_SUCCESS: Successful operation, but requires additional interaction
    """
    CRITICAL = -2
    ERROR = -1
    STATUS = 0
    SUCCESS = 1
    PARTIAL_SUCCESS = 2


async def send_websocket_response(websocket: websockets.WebSocketServerProtocol, status: WebsocketResponseCode,
                                  message: str):
    await websocket.send(json.dumps({
        "status": status.value
        , "payload": message}
    ))


async def reconnect_user(websocket) -> str:
    try:
        token = await asyncio.wait_for(websocket.recv(), timeout=3)
    except asyncio.TimeoutError:
        logging.warning("No token provided")
        raise websockets.exceptions.SecurityError("No token provided")

    if token not in common.known_users.values():
        logging.error("Unauthorized token %s", token)
        raise websockets.exceptions.SecurityError("Invalid token")

    try:
        login.recreate_session(token)
        await send_websocket_response(websocket, WebsocketResponseCode.SUCCESS, token)
    except login.UserAuthenticationException as e:
        raise websockets.exceptions.SecurityError(e)

    logging.info(f"Session created for {token}")
    return token


async def create_user(websocket) -> str:
    user = await asyncio.wait_for(websocket.recv(), timeout=WEBSOCKET_TIMEOUT)
    credentials = await asyncio.wait_for(websocket.recv(), timeout=WEBSOCKET_TIMEOUT)
    remember_me = True if await asyncio.wait_for(websocket.recv(), timeout=WEBSOCKET_TIMEOUT) else False
    try:
        token, duo_auth_code = login.sign_in(user, credentials, remember_me)
        if duo_auth_code is not None:
            await send_websocket_response(websocket, WebsocketResponseCode.PARTIAL_SUCCESS, duo_auth_code)
            login.duo_auth(token, remember_me)

        await send_websocket_response(websocket, WebsocketResponseCode.SUCCESS, token)
    except login.UserAuthenticationException as e:
        raise websockets.exceptions.SecurityError(e)

    return token


async def handle_search_classes(websocket, token) -> None:
    term = await asyncio.wait_for(websocket.recv(), timeout=WEBSOCKET_TIMEOUT)
    subject = await asyncio.wait_for(websocket.recv(), timeout=WEBSOCKET_TIMEOUT)
    class_number = await asyncio.wait_for(websocket.recv(), timeout=WEBSOCKET_TIMEOUT)
    logging.info("Received search request for %s %s %s", term, subject, class_number)
    try:
        result = schedule.search_classes(term, subject, class_number, token)
    except selenium.common.WebDriverException as e:  # silently log error and continue
        logging.exception(e)
        await send_websocket_response(websocket, WebsocketResponseCode.ERROR, "Could not search classes")
        return

    await send_websocket_response(websocket, WebsocketResponseCode.SUCCESS, str(result))


def handle_sign_out(token) -> str:
    return login.sign_out(token)


async def process_requests(websocket, token, tg):
    while True:
        message = await websocket.recv()
        response: str
        match message:
            case "SEARCH":
                logging.info("Received search request for user %s", token)
                await handle_search_classes(websocket, token)
            case "SIGN OUT":
                logging.info("Received sign out request for user %s", token)
                handle_sign_out(token)
                await websocket.close()
                await tg.__aexit__(None, None, None)
                return
            case "QUIT":
                logging.info("Quit received for user %s", token)
                common.delete_session(token)
                await websocket.close()
                await tg.__aexit__(None, None, None)
                return
            case _:
                await send_websocket_response(websocket, WebsocketResponseCode.ERROR, "Invalid request")
                continue


async def heartbeat(websocket, token, tg):
    while True:
        await asyncio.sleep(BPM * 60)
        logging.debug("Checking pulse for user %s", token)

        # TODO: Add check for idle warning and attempt to bypass
        if common.verify_signed_on(token):
            logging.debug("Pulse check passed for user %s", token)
        else:
            logging.warning("Pulse check failed for user %s", token)
            await websocket.close(reason="Dead session. Reauthenticate!")
            await tg.__aexit__(None, None, None)
            return


async def connect(websocket: websockets.WebSocketServerProtocol, path: str):
    logging.debug(path)
    token = ''
    try:
        if path == '/reconnect':
            logging.info("Received reconnect request")
            token = await reconnect_user(websocket)
        elif path == '/login':
            logging.info("Received login request")
            token = await create_user(websocket)
        else:
            logging.warning("Invalid path")
            await websocket.close(code=1002, reason="Invalid path")
            return

        try:
            async with asyncio.TaskGroup() as tg:
                tg.create_task(process_requests(websocket, token, tg))
                tg.create_task(heartbeat(websocket, token, tg))
        except ExceptionGroup as e:
            logging.exception(e)
            raise e.exceptions[0]

        logging.debug("Connection loop closed. Bye bye")
    except websockets.exceptions.SecurityError as e:
        logging.info(f"Closing connection because of authentication error: {e}")
        login.sign_out(token)
        await websocket.close(code=1002, reason=str(e))
        return
    except websockets.exceptions.ConnectionClosed as e:
        logging.warning(f"Connection closed unexpectedly: {e}")
        common.delete_session(token)
        return
    except TimeoutError:
        logging.warning("Response timed out")
        common.delete_session(token)
        await websocket.close(code=1002, reason="Response timed out")
        return
    except Exception as e:
        logging.exception(e)
        common.delete_session(token)
        await websocket.close(code=1011, reason="Internal server error")
        return


async def main():
    async with websockets.serve(connect, "localhost", 8765):
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())
