from fastapi import FastAPI

from scraper import login

app = FastAPI()


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/login/username={email}&credentials={password}")
async def authorize(email, password):
    return login.sign_in(email, password)
