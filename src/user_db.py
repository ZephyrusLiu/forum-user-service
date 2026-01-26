from sqlalchemy import create_engine, Table, Column, Integer, String, MetaData, DateTime, Enum, ForeignKey
from sqlalchemy.sql import func
import os

metadata = MetaData()

def get_db_url():
    host = os.environ["DB_HOST"]
    name = os.environ["DB_NAME"]
    username = os.environ["DB_USERNAME"]
    password = os.environ["DB_PASS"]

    return "mysql+pymysql://{}:{}@{}/{}".format(username,password,host,name)

engine = create_engine(get_db_url(), echo=True)
metadata.create_all(engine)

users_table = Table(
    "users",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("firstName", String(100), nullable=False),
    Column("lastName", String(100), nullable=False),
    Column("joinDate", DateTime, server_default=func.now(), nullable=False),
    Column("email", String(255), nullable=False, unique=True),
    Column("type", Enum("user", "admin", "super"), nullable=False, server_default="user"),
    Column("status", Enum("active", "banned", "unverified"), nullable=False, server_default="unverified"),
    Column("passHash", String(255), nullable=False),
    Column(
        "profileS3Key",
        String(1024),
        nullable=False,
        server_default=os.environ["DEFAULT_PROFILE_KEY"]
    ),
)
