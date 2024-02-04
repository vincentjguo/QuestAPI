import logging
from typing import Annotated

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm

from api.scraper import login, schedule, common

app = FastAPI()

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="authenticate",
    scopes={"remember_me": "Remember current user credentials"},
)


async def validate_token(token: Annotated[str, Depends(oauth2_scheme)]) -> str:
    """
    Validates token
    :param token: provided bearer token
    :return: provided token if valid
    """
    if token not in common.driver_list:
        logging.error("Unauthorized token %s", token)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials, authenticate first!",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not common.verify_signed_on(token):
        logging.error("User with token %s is stale. Authentication needed", token)
        raise HTTPException(status_code=409, detail="User signed out. Reauthenticate!")

    logging.info("Token %s authenticated successfully!", token)
    return token


@app.post("/authenticate")
async def authenticate(form_data: Annotated[OAuth2PasswordRequestForm, Depends()]):
    logging.info("Received authentication request for user %s", form_data.username)
    response = login.sign_in(form_data.username, form_data.password, "remember_me" in form_data.scopes)
    if not response:
        logging.error("Sign in failed for %s", form_data.username)
        raise HTTPException(status_code=401, detail="Sign in failed")

    return {"access_token": response, "token_type": "bearer"}


@app.get("/search/{term}&{subject}&{class_number}")
async def search_classes(term, subject, class_number, token: Annotated[str, Depends(validate_token)]):
    logging.info("Received search request for %s %s %s", term, subject, class_number)
    result = schedule.search_classes(term, subject, class_number, token)
    # TODO: Add check for if user is signed out
    return result


@app.get("/sign_out")
async def sign_out(token: Annotated[str, Depends(validate_token)]):
    logging.info("Received sign out request for user %s", token)
    return login.sign_out(token)

@app.get("/pulse")
async def pulse(token: Annotated[str, Depends(validate_token)]):
    logging.info("Received pulse check for user %s", token)
    if not common.verify_signed_on(token):
        raise HTTPException(status_code=409, detail="User signed out. Reauthenticate!")
    return token
