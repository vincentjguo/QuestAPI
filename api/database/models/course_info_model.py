from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Section(Base):
    __tablename__ = 'sections'

    id = Column(Integer, primary_key=True)
    section_type = Column(String)
    section_number = Column(String)
    location = Column(String)
    instructor = Column(String)
    course = Column(String, ForeignKey('courses.id'))

    def __init__(self, section_type, section_number, location, instructor, **kw):
        super().__init__(**kw)
        self.section_type = section_type
        self.section_number = section_number
        self.location = location
        self.instructor = instructor

    def get_section_name(self) -> str:
        return f"{self.section_type} {self.section_number}"

    def get_section_info(self) -> dict:
        return {self.get_section_name(): [self.location, self.instructor]}

    def __repr__(self):
        return f"{self.section_type} {self.section_number} {self.location} {self.instructor}"


class Course(Base):
    __tablename__ = 'courses'

    id = Column(String, primary_key=True)
    term = Column(String, ForeignKey('terms.id'))
    subject = Column(String)
    code = Column(String)
    sections = relationship('Section', backref='course_ref')

    def __init__(self, term, subject, code, **kw):
        super().__init__(**kw)
        self.id = f"{term} {subject} {code}"
        self.term = term
        self.subject = subject
        self.code = code

    def get_sections(self) -> dict:
        section_info = {}
        for section in self.sections:
            section_info.update(section.get_section_info())
        return section_info

    def add_section(self, section: Section) -> None:
        self.sections.append(section)

    def __repr__(self):
        return f"{self.term} {self.subject} {self.code} {str(self.sections)}"


class Term(Base):
    __tablename__ = 'terms'

    id = Column(String, primary_key=True)
    courses = relationship('Course', backref='term_ref')

    def __init__(self, id, **kw):
        super().__init__(**kw)
        self.id = id

    def __repr__(self):
        return f"{self.id}"

