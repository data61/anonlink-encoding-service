import enum
import os
import time

from sqlalchemy import (Column, create_engine, Enum, ForeignKey,
                        Integer, JSON, LargeBinary, String)
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.ext.declarative import declarative_base


try:
    _DB_URI = os.environ['CLKHASH_SERVICE_DB_URI']
except KeyError as _e:
    _msg = 'Unset environment variable CLKHASH_SERVICE_DB_URI.'
    raise KeyError(_msg) from _e


engine = create_engine(_DB_URI)
db_session = scoped_session(sessionmaker(autocommit=False,
                                         autoflush=False,
                                         bind=engine))
Base = declarative_base()


class ClkStatus(enum.Enum):
    QUEUED = 'queued'
    IN_PROGRESS = 'in-progress'
    DONE = 'done'
    INVALID_DATA = 'invalid-data'
    ERROR = 'error'


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
    pii = Column(JSON)  # Future: make own table if having scale issues?
    hash = Column(LargeBinary)


def init_db():
    Base.metadata.create_all(bind=engine)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("command", help="Command to run")
    parser.add_argument("-s", "--sleep", help="Delay in seconds before initializing database",
                        type=float, default=1)
    args = parser.parse_args()
    time.sleep(args.sleep)

    if args.command == 'init':
        print("Initialising database...")
        init_db()
    else:
        print('Command not recognized init')
