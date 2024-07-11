import asyncio
import json
import logging
from asyncio import CancelledError
from enum import IntEnum

import selenium.common
import websockets

from .database import db
from .scraper import schedule, common
from .scraper.schedule import ScheduleException
from .scraper.scraper import Scraper, UserAuthenticationException
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


async def reconnect_user(websocket: websockets.WebSocketServerProtocol, scraper: Scraper) -> None:
    try:
        scraper.token.set_token(await asyncio.wait_for(websocket.recv(), timeout=3))
    except asyncio.TimeoutError:
        logging.warning("No token provided")
        raise websockets.exceptions.SecurityError("No token provided")

    if not scraper.token.verify_token():
        logging.error("Unauthorized token %s", scraper.token)
        raise websockets.exceptions.SecurityError("Invalid token")

    try:
        scraper.recreate_session()
        await send_websocket_response(websocket, WebsocketResponseCode.SUCCESS, scraper.token.get_token())
    except UserAuthenticationException as e:
        handle_sign_out(e.token.get_token())
        raise websockets.exceptions.SecurityError(e)

    logging.info(f"Session created for {scraper.token}")


async def create_user(websocket: websockets.WebSocketServerProtocol, scraper: Scraper) -> None:
    user = await asyncio.wait_for(websocket.recv(), timeout=WEBSOCKET_TIMEOUT)
    credentials = await asyncio.wait_for(websocket.recv(), timeout=WEBSOCKET_TIMEOUT)
    remember_me = True if await asyncio.wait_for(websocket.recv(), timeout=WEBSOCKET_TIMEOUT) == "true" else False
    try:
        duo_auth_code = await scraper.sign_in(user, credentials, remember_me)
        if duo_auth_code is not None:
            await send_websocket_response(websocket, WebsocketResponseCode.PARTIAL_SUCCESS, duo_auth_code)
            await scraper.duo_auth(remember_me)

        await send_websocket_response(websocket, WebsocketResponseCode.SUCCESS, scraper.token.get_token())
    except UserAuthenticationException as e:
        handle_sign_out(e.token.get_token())
        raise websockets.exceptions.SecurityError(e)


async def handle_search_classes(websocket: websockets.WebSocketServerProtocol, scraper: Scraper) -> None:
    term = await asyncio.wait_for(websocket.recv(), timeout=WEBSOCKET_TIMEOUT)
    subject = await asyncio.wait_for(websocket.recv(), timeout=WEBSOCKET_TIMEOUT)
    class_number = await asyncio.wait_for(websocket.recv(), timeout=WEBSOCKET_TIMEOUT)
    logging.info("Received search request for %s %s %s", term, subject, class_number)
    try:
        result = db.get_course_info(term, subject, class_number)
        if result is None:
            logging.info("Course info not found in database. Searching...")
            result = await schedule.search_classes(scraper, term, subject, class_number)
            db.upsert_course_info(term, result)
    except selenium.common.WebDriverException as e:  # silently log error and continue
        logging.exception(e)
        await send_websocket_response(websocket, WebsocketResponseCode.ERROR, "Could not search classes")
        return
    except ScheduleException as e:
        await send_websocket_response(websocket, WebsocketResponseCode.ERROR, str(e))
        return

    await send_websocket_response(websocket, WebsocketResponseCode.SUCCESS, str(result.get_sections()))


def handle_sign_out(scraper: Scraper) -> str:
    return scraper.sign_out()


async def process_requests(websocket: websockets.WebSocketServerProtocol, scraper: Scraper) -> None:
    try:
        while True:
            message = await websocket.recv()
            response: str
            match message:
                case "SEARCH":
                    logging.info("Received search request for user %s", scraper.token)
                    await handle_search_classes(websocket, scraper)
                case "SIGN OUT":
                    logging.info("Received sign out request for user %s", scraper.token)
                    handle_sign_out(scraper)
                    await websocket.close()
                    raise CancelledError("User signed out")
                case "QUIT":
                    logging.info("Quit received for user %s", scraper.token)
                    await websocket.close()
                    raise CancelledError("User quit")
                case _:
                    await send_websocket_response(websocket, WebsocketResponseCode.ERROR, "Invalid request")
                    continue
    except asyncio.CancelledError:
        logging.debug("Request processing task cancelled")
        return


async def heartbeat(scraper: Scraper):
    try:
        while True:
            await asyncio.sleep(BPM * 60)
            logging.debug("Checking pulse for user %s", scraper.token)

            # TODO: Add check for idle warning and attempt to bypass
            if scraper.verify_signed_on():
                logging.debug("Pulse check passed for user %s", scraper.token)
            else:
                logging.warning("Pulse check failed for user %s", scraper.token)
                raise websockets.exceptions.SecurityError("Dead session. Reauthenticate!")
    except asyncio.CancelledError:
        logging.debug("Heartbeat task cancelled")
        return


async def begin_connection_loop(websocket: websockets.WebSocketServerProtocol, scraper: Scraper):
    try:
        async with asyncio.TaskGroup() as tg:
            tasks = [
                tg.create_task(process_requests(websocket, scraper), name=f'{scraper.token.get_token()}-process'),
                tg.create_task(heartbeat(scraper), name=f'{scraper.token.get_token()}-heartbeat')
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
            scraper = Scraper(token)
            if path == '/reconnect':
                logging.info("Received reconnect request")
                await reconnect_user(websocket, scraper)
            elif path == '/login':
                logging.info("Received login request")
                await create_user(websocket, scraper)
            else:
                logging.warning("Invalid path")
                await websocket.close(code=1002, reason="Invalid path")
                return

            await begin_connection_loop(websocket, scraper)

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
