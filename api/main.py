import json
import logging
import secrets
from typing import Annotated

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
import asyncio
import websockets

from api.scraper import login, schedule, common

# app = FastAPI()

# oauth2_scheme = OAuth2PasswordBearer(
#     tokenUrl="authenticate",
#     scopes={"remember_me": "Remember current user credentials"},
# )

BPM = 1


async def reconnect_user(websocket) -> str:
    try:
        token = await asyncio.wait_for(websocket.recv(), timeout=3)
    except asyncio.TimeoutError:
        logging.warning("No token provided")
        raise websockets.exceptions.SecurityError("ERROR: No token provided")

    if token not in common.known_users.values():
        logging.error("Unauthorized token %s", token)
        raise websockets.exceptions.SecurityError("ERROR: Invalid token")

    try:
        login.recreate_session(token)
        await websocket.send(token)
    except login.UserAuthenticationException as e:
        raise websockets.exceptions.SecurityError(e)

    logging.info(f"Session created for {token}")
    return token


async def create_user(websocket, token) -> str:
    user = await asyncio.wait_for(websocket.recv(), timeout=6)
    credentials = await asyncio.wait_for(websocket.recv(), timeout=6)
    remember_me = True if await asyncio.wait_for(websocket.recv(), timeout=6) else False
    try:
        duo_auth_code = login.sign_in(user, credentials, remember_me, token)
        await websocket.send(json.dumps([token, duo_auth_code]))
        if duo_auth_code is not None:
            login.duo_auth(token, remember_me)
    except login.UserAuthenticationException:
        raise websockets.exceptions.SecurityError("ERROR: Sign in failed")

    return token


async def handle_search_classes(websocket, token) -> str:
    term = await asyncio.wait_for(websocket.recv(), timeout=6)
    subject = await asyncio.wait_for(websocket.recv(), timeout=6)
    class_number = await asyncio.wait_for(websocket.recv(), timeout=6)
    logging.info("Received search request for %s %s %s", term, subject, class_number)
    result = schedule.search_classes(term, subject, class_number, token)

    return json.dumps(result)


def handle_sign_out(token) -> str:
    return login.sign_out(token)


async def process_requests(websocket, token, tg):
    while True:
        message = await websocket.recv()
        response: str
        match message:
            case "SEARCH":
                logging.info("Received search request for user %s", token)
                response = await handle_search_classes(websocket, token)
            case "SIGN OUT":
                logging.info("Received sign out request for user %s", token)
                response = handle_sign_out(token)
            case "QUIT":
                logging.info("Terminate received for user %s", token)
                common.delete_session(token)
                await websocket.close()
                await tg.__aexit__(None, None, None)
                return
            case _:
                await websocket.send("ERROR: Invalid request")
                continue

        await websocket.send(response)


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
    token: str = secrets.token_urlsafe(16)
    logging.debug(path)
    try:
        if path == '/reconnect':
            logging.info("Received reconnect request")
            token = await reconnect_user(websocket)
        elif path == '/login':
            logging.info("Received login request")
            await create_user(websocket, token)
        else:
            logging.warning("Invalid path")
            await websocket.close(reason="Invalid path")
            return

        try:
            async with asyncio.TaskGroup() as tg:
                tg.create_task(process_requests(websocket, token, tg))
                tg.create_task(heartbeat(websocket, token, tg))
        except ExceptionGroup as e:
            logging.exception(e)
            raise e.exceptions[0]

    except websockets.exceptions.SecurityError as e:
        logging.info(f"Closing connection because of authentication error: {e}")
        await websocket.close(reason=str(e))
        return
    except websockets.exceptions.ConnectionClosed as e:
        logging.warning(f"Connection closed unexpectedly: {e}")
        return
    except TimeoutError:
        logging.warning("Response timed out")
        await websocket.close(reason="Response timed out")
        return
    except Exception as e:
        logging.exception(e)
        if logging.root.level != logging.DEBUG:
            handle_sign_out(token)
        await websocket.close(code=1011, reason="Internal server error")
        return


async def main():
    async with websockets.serve(connect, "localhost", 8765):
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    # logger = logging.getLogger('websockets')
    # logger.addHandler(logging.StreamHandler())
    asyncio.run(main())

#
# async def validate_token(token: Annotated[str, Depends(oauth2_scheme)]) -> str:
#     """
#     Validates token
#     :param token: provided bearer token
#     :return: provided token if valid
#     """
#     if token not in common.driver_list.keys():
#         logging.error("Unauthorized token %s", token)
#         raise HTTPException(
#             status_code=status.HTTP_401_UNAUTHORIZED,
#             detail="Invalid authentication credentials, authenticate first!",
#             headers={"WWW-Authenticate": "Bearer"},
#         )
#     if not common.verify_signed_on(token):
#         logging.error("User with token %s is stale. Authentication needed", token)
#         raise HTTPException(status_code=409, detail="User signed out. Reauthenticate!")
#
#     logging.info("Token %s authenticated successfully!", token)
#     return token
#
#
# @app.post("/authenticate")
# async def authenticate(form_data: Annotated[OAuth2PasswordRequestForm, Depends()]):
#     logging.info("Received authentication request for user %s", form_data.username)
#     response = login.sign_in(form_data.username, form_data.password, "remember_me" in form_data.scopes)
#     if not response:
#         logging.error("Sign in failed for %s", form_data.username)
#         raise HTTPException(status_code=401, detail="Sign in failed")
#
#     return {"access_token": response, "token_type": "bearer"}
#
#
# @app.get("/search/{term}&{subject}&{class_number}")
# async def search_classes(term, subject, class_number, token: Annotated[str, Depends(validate_token)]):
#     logging.info("Received search request for %s %s %s", term, subject, class_number)
#     result = schedule.search_classes(term, subject, class_number, token)
#     # TODO: Add check for if user is signed out
#     return result
#
#
# @app.get("/sign_out")
# async def sign_out(token: Annotated[str, Depends(validate_token)]):
#     logging.info("Received sign out request for user %s", token)
#     return login.sign_out(token)
#
# @app.get("/pulse")
# async def pulse(token: Annotated[str, Depends(validate_token)]):
#     logging.info("Received pulse check for user %s", token)
#     if not common.verify_signed_on(token):
#         raise HTTPException(status_code=409, detail="User signed out. Reauthenticate!")
#     return token
