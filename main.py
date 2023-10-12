from typing import Annotated

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm, SecurityScopes
from pydantic import BaseModel, ValidationError

from scraper import login, schedule, common

app = FastAPI()

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="authenticate",
    scopes={"remember_me": "Remember current user credentials"},
)


async def validate_token(token: Annotated[str, Depends(oauth2_scheme)]):
    if token not in common.driver_list:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials, authenticate first!",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if common.verify_signed_on(common.driver_list[token]):
        raise HTTPException(status_code=408, detail="User signed out")

    return token


@app.post("/authenticate")
async def authenticate(form_data: Annotated[OAuth2PasswordRequestForm, Depends()]):
    response = login.sign_in(form_data.username, form_data.password, "remember_me" in form_data.scopes)
    if not response:
        raise HTTPException(status_code=401, detail="Sign in failed")

    return {"access_token": response, "token_type": "bearer"}


@app.get("/search/{term}&{subject}&{class_number}")
async def search_classes(term, subject, class_number, token: Annotated[str, Depends(validate_token)]):
    return schedule.search_classes(term, subject, class_number, token)
