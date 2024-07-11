import logging
import sqlite3

from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from api.database.models.course_info_model import Course, Base, Term

database = 'laminarflow.db'

logger = logging.getLogger(__name__)
sqlalchemy_logger = logging.getLogger('sqlalchemy.engine')
sqlalchemy_logger.setLevel(logging.INFO)
for handler in logger.handlers:
    sqlalchemy_logger.addHandler(handler)

engine = create_engine(f'sqlite:///{database}')
Base.metadata.create_all(engine)


def get_course_info(term: str, subject: str, number: str):
    try:
        with Session(engine) as session:
            return (session.query(Course)
                    .options(joinedload(Course.sections))  # Eagerly load the 'sections' relationship
                    .filter_by(term=term, subject=subject, code=number)
                    .first())
    except SQLAlchemyError as e:
        logger.exception(e)
        return None


def upsert_course_info(term: str, course: Course):
    try:
        with Session(engine) as session:
            if not session.query(Term).filter_by(id=term).count():
                logger.info("Term %s not found, adding...", term)
                session.add(Term(term))
            session.add(course)
            session.commit()

    except SQLAlchemyError as e:
        logger.exception(e)


def save_cookies(token: str, cookies: bytes):
    try:
        with sqlite3.connect(database) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS cookies (token TEXT PRIMARY KEY, cookies TEXT)")
            conn.execute("INSERT OR REPLACE INTO cookies (token, cookies) VALUES (?, ?)", (token, cookies))
    except sqlite3.Error as e:
        logger.exception(e)


def load_cookies(token: str) -> bytes:
    try:
        with sqlite3.connect(database) as conn:
            return conn.execute("SELECT cookies FROM cookies WHERE token = ?", (token,)).fetchone()
    except sqlite3.Error as e:
        logger.exception(e)
        raise e

def remove_cookies(token: str):
    try:
        with sqlite3.connect(database) as conn:
            conn.execute("DELETE FROM cookies WHERE token = ?", (token,))
    except sqlite3.Error as e:
        logger.exception(e)
        raise e

