import asyncio
import json
import logging
from asyncio import CancelledError
from enum import IntEnum

import selenium.common
import websockets

from .database import db
from .scraper import login, schedule, common
from .scraper.schedule import ScheduleException
from .token_manager import TokenManager

BPM = 1
WEBSOCKET_TIMEOUT = 3


class WebsocketResponseCode(IntEnum):
    """
    Enum for websocket response codes

    CRITICAL
        Connection cannot continue, will be shutdown
    ERROR
        Error occurred, connection will continue
    STATUS
        Status message, process not finished
    SUCCESS
        Successful operation, ready for next query
    PARTIAL_SUCCESS
        Successful operation, but requires additional interaction
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


async def reconnect_user(websocket: websockets.WebSocketServerProtocol, token: TokenManager) -> None:
    try:
        token.set_token(await asyncio.wait_for(websocket.recv(), timeout=3))
    except asyncio.TimeoutError:
        logging.warning("No token provided")
        raise websockets.exceptions.SecurityError("No token provided")

    if not token.verify_token():
        logging.error("Unauthorized token %s", token)
        raise websockets.exceptions.SecurityError("Invalid token")

    try:
        login.recreate_session(token)
        await send_websocket_response(websocket, WebsocketResponseCode.SUCCESS, token.get_token())
    except login.UserAuthenticationException as e:
        handle_sign_out(e.token.get_token())
        raise websockets.exceptions.SecurityError(e)

    logging.info(f"Session created for {token.get_token()}")


async def create_user(websocket: websockets.WebSocketServerProtocol, token: TokenManager) -> None:
    user = await asyncio.wait_for(websocket.recv(), timeout=WEBSOCKET_TIMEOUT)
    credentials = await asyncio.wait_for(websocket.recv(), timeout=WEBSOCKET_TIMEOUT)
    remember_me = True if await asyncio.wait_for(websocket.recv(), timeout=WEBSOCKET_TIMEOUT) == "true" else False
    try:
        duo_auth_code = await login.sign_in(user, credentials, remember_me, token)
        if duo_auth_code is not None:
            await send_websocket_response(websocket, WebsocketResponseCode.PARTIAL_SUCCESS, duo_auth_code)
            await login.duo_auth(token, remember_me)

        await send_websocket_response(websocket, WebsocketResponseCode.SUCCESS, token.get_token())
    except login.UserAuthenticationException as e:
        handle_sign_out(e.token.get_token())
        raise websockets.exceptions.SecurityError(e)


async def handle_search_classes(websocket: websockets.WebSocketServerProtocol, token: str) -> None:
    term = await asyncio.wait_for(websocket.recv(), timeout=WEBSOCKET_TIMEOUT)
    subject = await asyncio.wait_for(websocket.recv(), timeout=WEBSOCKET_TIMEOUT)
    class_number = await asyncio.wait_for(websocket.recv(), timeout=WEBSOCKET_TIMEOUT)
    logging.info("Received search request for %s %s %s", term, subject, class_number)
    try:
        result = db.get_course_info(term, subject, class_number)
        if result is None:
            logging.info("Course info not found in database. Searching...")
            result = await schedule.search_classes(term, subject, class_number, token)
            db.upsert_course_info(term, result)
    except selenium.common.WebDriverException as e:  # silently log error and continue
        logging.exception(e)
        await send_websocket_response(websocket, WebsocketResponseCode.ERROR, "Could not search classes")
        return
    except ScheduleException as e:
        await send_websocket_response(websocket, WebsocketResponseCode.ERROR, str(e))
        return

    await send_websocket_response(websocket, WebsocketResponseCode.SUCCESS, str(result.get_sections()))


def handle_sign_out(token: str) -> str:
    return login.sign_out(token)


async def process_requests(websocket: websockets.WebSocketServerProtocol, token: str) -> None:
    try:
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
                    raise CancelledError("User signed out")
                case "QUIT":
                    logging.info("Quit received for user %s", token)
                    await websocket.close()
                    raise CancelledError("User quit")
                case _:
                    await send_websocket_response(websocket, WebsocketResponseCode.ERROR, "Invalid request")
                    continue
    except asyncio.CancelledError:
        logging.debug("Request processing task cancelled")
        return


async def heartbeat(token: str):
    try:
        while True:
            await asyncio.sleep(BPM * 60)
            logging.debug("Checking pulse for user %s", token)

            # TODO: Add check for idle warning and attempt to bypass
            if common.verify_signed_on(token):
                logging.debug("Pulse check passed for user %s", token)
            else:
                logging.warning("Pulse check failed for user %s", token)
                raise websockets.exceptions.SecurityError("Dead session. Reauthenticate!")
    except asyncio.CancelledError:
        logging.debug("Heartbeat task cancelled")
        return


async def begin_connection_loop(websocket: websockets.WebSocketServerProtocol, token: TokenManager):
    try:
        async with asyncio.TaskGroup() as tg:
            tasks = [
                tg.create_task(process_requests(websocket, token.get_token()), name=f'{token.get_token()}-process'),
                tg.create_task(heartbeat(token.get_token()), name=f'{token.get_token()}-heartbeat')
            ]
            finished, unfinished = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in unfinished:
                task.cancel()
                await task
    except ExceptionGroup as e:
        logging.debug(e)
        raise e.exceptions[0]
    logging.info("Connection loop closed. Bye bye")


async def connect(websocket: websockets.WebSocketServerProtocol, path: str):
    logging.debug(path)
    try:
        with TokenManager() as token:
            if path == '/reconnect':
                logging.info("Received reconnect request")
                await reconnect_user(websocket, token)
            elif path == '/login':
                logging.info("Received login request")
                await create_user(websocket, token)
            else:
                logging.warning("Invalid path")
                await websocket.close(code=1002, reason="Invalid path")
                return

            await begin_connection_loop(websocket, token)

    except websockets.exceptions.SecurityError as e:
        logging.warning(f"Closing connection because of authentication error: {e}")
        await websocket.close(code=1002, reason=str(e))
        return
    except websockets.exceptions.ConnectionClosed as e:
        logging.warning(f"Connection closed unexpectedly: {e}")
        return
    except TimeoutError:
        logging.warning("Response timed out")
        await websocket.close(code=1002, reason="Response timed out")
        return
    except Exception as e:
        logging.exception(e)
        await websocket.close(code=1011, reason="Internal server error")
        return
