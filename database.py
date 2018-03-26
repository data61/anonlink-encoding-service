import enum
import os
import sys

from sqlalchemy import (Column, create_engine, Enum, ForeignKey,
                        Integer, JSON, LargeBinary, String)
from sqlalchemy.orm import relationship, scoped_session, sessionmaker
from sqlalchemy.ext.declarative import declarative_base


try:
    _DB_URI = os.environ['CLK_SERVICE_DB_URI']
except KeyError as _e:
    _msg = 'Unset environment variable CLK_SERVICE_DB_URI.'
    raise KeyError(_msg) from _e


engine = create_engine(_DB_URI)
db_session = scoped_session(sessionmaker(autocommit=False,
                                         autoflush=False,
                                         bind=engine))
Base = declarative_base()


class ClkStatus(enum.Enum):
    CLK_QUEUED = 'queued'
    CLK_IN_PROGRESS = 'in progress'
    CLK_DONE = 'done'
    CLK_INVALID_DATA = 'invalid data'
    CLK_ERROR = 'error'


class Project(Base):
    __tablename__ = 'projects'

    id = Column(String, primary_key=True)
    schema = Column(JSON, nullable=False)
    keys = Column(JSON, nullable=False)
    clk_count = Column(Integer, nullable=False, server_default='0')


class Clk(Base):
    __tablename__ = 'clks'

    project_id = Column(String, ForeignKey(Project.id, ondelete="CASCADE"), primary_key=True)
    index = Column(Integer, primary_key=True)
    status = Column(Enum(ClkStatus), nullable=False)
    err_msg = Column(String)
    pii = Column(JSON)  #  TODO: make own table if having scale issues?
    hash = Column(LargeBinary)


def init_db():
    Base.metadata.create_all(bind=engine)


if __name__ == '__main__':
    if len(sys.argv) == 2 and sys.argv[1] == 'init':
        init_db()
    else:
        'To create database: python database.py init'
