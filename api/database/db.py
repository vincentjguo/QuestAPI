import logging
import os
import sqlite3

from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload, sessionmaker

from api.database.models.course_info_model import Course, Base, Term

database = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'laminarflow.db')

logger = logging.getLogger(__name__)
sqlalchemy_logger = logging.getLogger('sqlalchemy.engine')
sqlalchemy_logger.setLevel(logging.INFO)
for handler in logger.handlers:
    sqlalchemy_logger.addHandler(handler)


engine = create_engine(f'sqlite:///{database}')
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine, expire_on_commit=False)


def get_course_info(term: str, subject: str, code: str):
    logger.info("Getting course info for %s %s %s", term, subject, code)
    try:
        with Session() as session:
            return (session.query(Course)
                    .options(selectinload(Course.sections))  # Eagerly load the 'sections' relationship
                    .filter_by(term=term, subject=subject, code=code)
                    .first())
    except SQLAlchemyError as e:
        logger.exception(e)
        return None


def upsert_course_info(term: str, course: Course):
    try:
        logger.info("Upserting course %s", course.id)
        with Session() as session:
            if not session.query(Term).filter_by(id=term).count():
                logger.info("Term %s not found, adding...", term)
                session.add(Term(term))
            session.add(course)
            session.commit()

    except SQLAlchemyError as e:
        logger.exception(e)


def save_cookies(token: str, cookies: bytes):
    logger.info("Saving cookies for %s", token)
    try:
        with sqlite3.connect(database) as conn:
            conn.execute("UPDATE users SET cookies = ? WHERE token = ?", (cookies, token))
            # If the user was not already in the database, insert it
            if conn.total_changes == 0:
                conn.execute("INSERT INTO users (token, cookies) VALUES (?, ?)", (token, cookies))
    except sqlite3.Error as e:
        logger.exception(e)


def load_cookies(token: str) -> bytes:
    logger.info("Loading cookies for %s", token)
    try:
        with sqlite3.connect(database) as conn:
            return conn.execute("SELECT cookies FROM users WHERE token = ?", (token,)).fetchone()[0]
    except sqlite3.Error as e:
        logger.debug(e)
        raise e


def save_user(token: str, user: str):
    logger.info("Saving user %s", user)
    try:
        with sqlite3.connect(database) as conn:
            conn.execute("UPDATE users SET user = ? WHERE token = ?", (user, token))
    except sqlite3.Error as e:
        logger.exception(e)
        raise e


def load_users() -> dict:
    logger.info("Loading all users")
    try:
        with sqlite3.connect(database) as conn:
            users = {row[0]: row[1] for row in conn.execute("SELECT user, token FROM users")}
            logger.info("Loaded users ", users)
            return users
    except sqlite3.Error as e:
        logger.exception(e)
        raise e


def remove_user(token: str):
    logger.info("Removing user %s", token)
    try:
        with sqlite3.connect(database) as conn:
            conn.execute("DELETE FROM users WHERE token = ?", (token,))
    except sqlite3.Error as e:
        logger.exception(e)
        raise e
