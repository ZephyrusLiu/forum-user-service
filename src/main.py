from dotenv import load_dotenv
from pathlib import Path
import os
from flask import Flask, request, jsonify, abort
from sqlalchemy import create_engine, Table, Column, Integer, String, MetaData, select, insert
from werkzeug.security import generate_password_hash, check_password_hash
import jwt

load_dotenv(Path(__file__).resolve().parents[2].joinpath(".env"), override=True)
load_dotenv(Path(__file__).resolve().parents[1].joinpath(".env"), override=True)


JWT_SECRET = os.environ["JWT_SECRET"]


def get_db_url():
    host = os.environ["DB_HOST"]
    name = os.environ["DB_NAME"]
    username = os.environ["DB_USERNAME"]
    password = os.environ["DB_PASS"]

    return "mysql+pymysql://{}:{}@{}/{}".format(username,password,host,name)

app = Flask(__name__)
engine = create_engine(get_db_url(), echo=True)


@app.route("/health")
def health():
    return jsonify({"ok" : True, "message" : "system normal"}), 200


if __name__ == "__main__":
    app.run(port=5001, debug=True)



