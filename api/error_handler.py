from fastapi import HTTPException

from api.main import app


@app.exception_handler(Exception)
async def exception_callback(exc: Exception):
    print(exc)
    raise HTTPException(status_code=500, detail="Internal server error")
