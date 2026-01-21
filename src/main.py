from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2].joinpath(".env"), override=True)
load_dotenv(Path(__file__).resolve().parents[1].joinpath(".env"), override=True)

import os
from flask import Flask, request, jsonify, abort
from sqlalchemy import select, insert, update
from sqlalchemy.exc import IntegrityError, DBAPIError
from werkzeug.security import generate_password_hash, check_password_hash
import jwt

import secrets

#for debugging only
import code

from user_db import engine, users_table
from rmq import get_rmq_channel, publish_event

from message import RMessage, RErrorMessage

#TODO: blueprints for private and public routes?


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

#PUBLIC
@app.route("/users/login",methods = ["POST"])
def login():
    data = request.get_json()
    if not data:
        return RErrorMessage("Missing JSON body",400).get()

    try:
        email = data["email"]
        passw = data["password"]
    except KeyError:
        return RErrorMessage("Missing fields body",400).get()

    message = RErrorMessage()

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
                return RErrorMessage("Invalid credentials",401).get()

            if row.status == "banned":
                return RErrorMessage("Account banned",403).get()

            if not check_password_hash(row.passHash, passw):
                return RErrorMessage("Invalid credentials",401).get()

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

            message = RMessage().add("token",token)
            
    except Exception:
        app.logger.exception("login failed")
        message = RErrorMessage("Database error",503)

    return message.get()


@app.route("/users/health")
def health():
    return RMessage().msg("status normal").get()


@app.route("/users/verify", methods = ["GET"])
def verify_email():
    token = request.args.get("token", type=str)

    if token == None:
        return RErrorMessage("Missing token",400).get()

    entry = None

    for i,e in enumerate(active_tokens):
        if token == e["token"]:
            entry = e
            break

    if entry == None:
        return RErrorMessage("Invalid token").get()

    user_id = entry["user_id"]

    message = RErrorMessage()

    try:
        with engine.begin() as conn:
            row = conn.execute(
                select(users_table.c.id).where(users_table.c.id == user_id)
            ).first()

            if not row:
                active_tokens.remove(entry)
                return RErrorMessage("User not found",404).get()

            result = conn.execute(
                update(users_table)
                .where(users_table.c.id == user_id)
                .values(status="active")
            )

            if result.rowcount != 1:
                return RErrorMessage("Verification failed",500).get()

        active_tokens.remove(entry)
        message = RMessage().msg("Email verified")

    except Exception:
        app.logger.exception("verify_email failed")
        message = RErrorMessage("Database error",503)

    return message.get()
        


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
        return RErrorMessage("Missing fields",400).get()


    message = RErrorMessage()
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

            message = RMessage(201).msg("New user registered").add("id",new_id)

    except IntegrityError as e:
        error_code = e.orig.args[0] if getattr(e, "orig", None) and getattr(e.orig, "args", None) else None

        text, code = ("Email already registered", 409) \
                if error_code == 1062 else \
                ("Database constraint error", 400)

        message = RErrorMessage(text,code)


    except DBAPIError:
        message = RErrorMessage("Database error",503)

    if new_id != None:
        handle_email(new_id, email)

    
    return message.get()

#PRIVATE
@app.route("/users/ping",methods = ["GET"])
def ping():
    return RMessage().msg("pong").get()


@app.route("/users/<int:user_id>/profile",methods = ["GET"])
def get_profile(user_id):

    message = RErrorMessage()

    stmt_user = select(
        users.c.id,
        users.c.firstName,
        users.c.lastName,
        users.c.joinDate,
        users.c.type,
        users.c.status,
        users.c.profileMediaID
    ).where(users.c.id == user_id)

    stmt_media = select(
        media.c.s3Bucket,
        media.c.s3Key
    ).where(media.c.id == bindparam("media_id"))

    try:
        with engine.begin() as conn:
            user = conn.execute(stmt_user).mappings().first()

            if not user:
                return RErrorMessage("User not found",404).get()

            profile_media = None
            if user["profileMediaID"] is not None:
                m = conn.execute(
                    stmt_media,
                    {"media_id": user["profileMediaID"]}
                ).mappings().first()

                if m:
                    profile_media = {
                        "s3Bucket": m["s3Bucket"],
                        "s3Key": m["s3Key"]
                    }

        return jsonify({
            "id": user["id"],
            "firstName": user["firstName"],
            "lastName": user["lastName"],
            "joinDate": user["joinDate"].isoformat(),
            "type": user["type"],
            "status": user["status"],
            "profileMediaID": user["profileMediaID"],
            "profileMedia": profile_media
        }), 200

    except DBAPIError:
        message = RErrorMessage("Database error",503)

    return message.get()

if __name__ == "__main__":
    app.run(port=5001, debug=True)



