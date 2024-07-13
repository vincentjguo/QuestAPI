import asyncio
import json
import logging
from asyncio import CancelledError
from enum import IntEnum

import websockets

from .session_manager import SessionManager, SessionException

WEBSOCKET_TIMEOUT = 3

logger = logging.getLogger("websocket")


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


async def process_requests(websocket: websockets.WebSocketServerProtocol, session: SessionManager) -> None:
    try:
        while True:
            message = await websocket.recv()
            response: str
            try:
                match message:
                    case "SEARCH":
                        term = await asyncio.wait_for(websocket.recv(), timeout=WEBSOCKET_TIMEOUT)
                        subject = await asyncio.wait_for(websocket.recv(), timeout=WEBSOCKET_TIMEOUT)
                        class_number = await asyncio.wait_for(websocket.recv(), timeout=WEBSOCKET_TIMEOUT)
                        await send_websocket_response(websocket,
                                                      WebsocketResponseCode.SUCCESS,
                                                      str(await session.handle_search_classes(term, subject,
                                                                                              class_number)))
                    case "SIGN OUT":
                        logger.info("Received sign out request for user")
                        session.handle_sign_out()
                        await websocket.close()
                        raise CancelledError("User signed out")
                    case "QUIT":
                        logger.info("Quit received for user")
                        await websocket.close()
                        raise CancelledError("User quit")
                    case _:
                        logger.warning("Invalid request")
                        await send_websocket_response(websocket, WebsocketResponseCode.ERROR, "Invalid request")
                        continue
            except SessionException as e:
                await send_websocket_response(websocket, WebsocketResponseCode.ERROR, str(e))
    except asyncio.CancelledError:
        logger.debug("Request processing task cancelled")
        return


async def begin_connection_loop(websocket: websockets.WebSocketServerProtocol, session: SessionManager):
    try:
        async with asyncio.TaskGroup() as tg:
            tasks = [
                tg.create_task(process_requests(websocket, session), name=f'{session.token}-process'),
            ]
            finished, unfinished = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in unfinished:
                task.cancel()
                await task
    except ExceptionGroup as e:
        logger.debug(e)
        raise e.exceptions[0]
    logger.info("Connection loop closed. Bye bye")


async def connect(websocket: websockets.WebSocketServerProtocol, path: str):
    logger.debug(path)
    with SessionManager() as session:
        try:
            if path == '/reconnect':
                logger.info("Received reconnect request")
                token = await asyncio.wait_for(websocket.recv(), timeout=WEBSOCKET_TIMEOUT)
                if token is None:
                    raise websockets.exceptions.SecurityError("No token provided")

                session.set_token(token)
                await send_websocket_response(websocket, WebsocketResponseCode.SUCCESS, await session.reconnect_user())
            elif path == '/login':
                logger.info("Received login request")
                user = await asyncio.wait_for(websocket.recv(), timeout=WEBSOCKET_TIMEOUT)
                credentials = await asyncio.wait_for(websocket.recv(), timeout=WEBSOCKET_TIMEOUT)
                remember_me = True if await asyncio.wait_for(websocket.recv(),
                                                             timeout=WEBSOCKET_TIMEOUT) == "true" else False
                if user is None or credentials is None:
                    raise websockets.exceptions.SecurityError("No credentials provided")

                token = await session.create_user(user, credentials, remember_me,
                                                  lambda duo_auth_code:
                                                  send_websocket_response(websocket,
                                                                          WebsocketResponseCode.PARTIAL_SUCCESS,
                                                                          duo_auth_code))
                await send_websocket_response(websocket, WebsocketResponseCode.SUCCESS, token)
            else:
                logger.warning("Invalid path")
                await websocket.close(code=1002, reason="Invalid path")
                return

            await begin_connection_loop(websocket, session)

        except websockets.exceptions.SecurityError as e:
            logger.warning(f"Closing connection because of authentication error: {e}")
            await websocket.close(code=1002, reason=str(e))
            return
        except websockets.exceptions.ConnectionClosed as e:
            logger.warning(f"Connection closed unexpectedly: {e}")
            return
        except asyncio.TimeoutError:
            logger.warning("No credentials provided")
            await websocket.close(code=1002, reason="No credentials provided")
            return
        except TimeoutError:
            logger.warning("Response timed out")
            await websocket.close(code=1002, reason="Response timed out")
            return
        except Exception as e:
            logger.exception(e)
            await websocket.close(code=1011, reason="Internal server error")
            return
