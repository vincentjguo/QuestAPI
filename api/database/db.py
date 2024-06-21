import logging
import sqlite3

from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from api.database.models.course_info_model import Course, Base, Term

course_info_db = 'course_info.db'

logger = logging.getLogger(__name__)
sqlalchemy_logger = logging.getLogger('sqlalchemy.engine')
sqlalchemy_logger.setLevel(logging.INFO)
for handler in logger.handlers:
    sqlalchemy_logger.addHandler(handler)

engine = create_engine('sqlite:///course_info.db')
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
