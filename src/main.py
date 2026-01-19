from dotenv import load_dotenv
from pathlib import Path
import os
from flask import Flask, request, jsonify, abort
from sqlalchemy import create_engine, Table, Column, Integer, String, MetaData, select, insert
from werkzeug.security import generate_password_hash, check_password_hash
import jwt


db_url = ""
JWT_SECRET = ""
load_dotenv(Path(__file__).resolve().parents[2].joinpath(".env"), override=True)

app = Flask(__name__)
#engine = create_engine(db_url, echo=True)


@app.route("/")
def ping():
    return jsonify({"ok" : True, "message" : "pong"}), 200


if __name__ == "__main__":
    app.run(port=5001, debug=True)
