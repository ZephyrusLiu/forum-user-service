from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2].joinpath(".env"), override=True)
load_dotenv(Path(__file__).resolve().parents[1].joinpath(".env"), override=True)

import os
from flask import Flask, request, jsonify, abort
from sqlalchemy import create_engine, select, insert, update
from sqlalchemy.exc import IntegrityError, DBAPIError
from werkzeug.security import generate_password_hash, check_password_hash
import jwt

import secrets

#for debugging only
import code

from user_db import engine, users_table
from rmq import get_rmq_channel, publish_event


app = Flask(__name__)

active_tokens = [] #TODO: expire tokens after 15 minutes


#code.interact(local=locals())

def handle_email(user_id, email):
    token = None
    try:
        token = secrets.token_urlsafe(32)
        publish_event("user.verify_email", 
                      {"userID" : user_id, "email" : email, "token" : token})

    except Exception as e: #TODO: make db table of emails to queue email sends?? or let unverified users to resend email??
        token = None

    if token != None:
        active_tokens.append({"user_id" : user_id, "token" : token})

@app.route("/users/ping",methods = ["GET"])
def ping():
    return jsonify({"message" : "pong"}), 200

@app.route("/users/login",methods = ["POST"])
def login():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Missing JSON body"}), 400

    try:
        email = data["email"]
        passw = data["password"]
    except KeyError:
        return jsonify({"error": "Missing fields"}), 400

    message = {"message" : "Unexpected error"}
    message_code = 501

    try:
        with engine.connect() as conn:
            row = conn.execute(
                select(
                    users_table.c.id,
                    users_table.c.passHash,
                    users_table.c.status,
                    users_table.c.type
                ).where(users_table.c.email == email)
            ).first()

            if row is None:
                return jsonify({"error": "Invalid credentials"}), 401

            if row.status == "banned":
                return jsonify({"error": "Account banned"}), 403

            if not check_password_hash(row.passHash, passw):
                return jsonify({"error": "Invalid credentials"}), 401

            JWT_SECRET = os.environ["JWT_SECRET"]
            JWT_ISSUER = "forum_user_service"

            token = jwt.encode(
                {
                    "sub": str(row.id),
                    "iss": JWT_ISSUER,

                    "id": row.id,
                    "type": row.type,
                    "status": row.status,
                },
                JWT_SECRET,
                algorithm="HS256"
            )
            
            message["token"], message["message"], message_code = token, "Login successful", 200

    except Exception:
        app.logger.exception("login failed")
        message["message"], message_code = token, "Database error", 503

    return jsonify(message), message_code


@app.route("/users/health")
def health():
    return jsonify({"ok" : True, "message" : "system normal"}), 200


@app.route("/users/verify", methods = ["GET"])
def verify_email():
    token = request.args.get("token", type=str)

    if token == None:
        return jsonify({"error" : "Missing token"}), 400

    entry = None

    for i,e in enumerate(active_tokens):
        if token == e["token"]:
            entry = e
            break

    if entry == None:
        return jsonify({"error" : "Invalid token"}), 400

    user_id = entry["user_id"]

    message = {"message" : "Unexpected error"}
    message_code = 501

    try:
        with engine.begin() as conn:
            row = conn.execute(
                select(users_table.c.id).where(users_table.c.id == user_id)
            ).first()

            if not row:
                active_tokens.remove(entry)
                return jsonify({"error": "User not found"}), 404

            result = conn.execute(
                update(users_table)
                .where(users_table.c.id == user_id)
                .values(status="active")
            )

            if result.rowcount != 1:
                return jsonify({"error": "Verification failed"}), 500

        active_tokens.remove(entry)

        message["message"], message_code = "Email verified", 200

    except Exception:
        app.logger.exception("verify_email failed")
        message["message"], message_code = "Database error", 503

    return jsonify(message), message_code
        


@app.route("/users/register", methods=["POST"])
def register():
    data = request.get_json()


    try:
        firstName = data["firstName"]
        lastName = data["lastName"]
        email = data["email"]
        passw = data["password"]
        passHash = generate_password_hash(passw)

    except KeyError:
        return jsonify({"error" : "Missing fields"}), 400


    message = {"message" : "Unexpected error"}
    message_code = 501
    new_id = None

    stmt = insert(users_table).values(
            firstName = firstName,
            lastName = lastName,
            email = email,
            passHash = passHash,
            )


    try:
        with engine.begin() as conn:
            result = conn.execute(stmt)

            new_id = result.inserted_primary_key[0]

            message["message"], message["id"], message_code = "New user registered", new_id, 201

    except IntegrityError as e:
        error_code = e.orig.args[0] if getattr(e, "orig", None) and getattr(e.orig, "args", None) else None

        message["message"], message_code = ("Email already registered", 409) \
                if error_code == 1062 else \
                ("Database constraint error", 400)

    except DBAPIError:
        message["message"], message_code = "Database error", 503

    if new_id != None:
        handle_email(new_id, email)

    
    return jsonify(message), message_code


if __name__ == "__main__":
    app.run(port=5001, debug=True)



