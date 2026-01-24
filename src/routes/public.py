from flask import request, Blueprint
import os
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
import secrets
import random
from sqlalchemy import select, insert, update, bindparam
from sqlalchemy.exc import IntegrityError, DBAPIError

from ..user_db import engine, users_table, media_table
from ..rmq import get_rmq_channel, publish_event
from utils.python.message import RMessage, RErrorMessage, RResponse


public_bp = Blueprint("public",__name__,url_prefix= "/users/")

JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ISSUER = "forum_user_service"
active_tokens = [] #TODO: expire tokens after 15 minutes

def _handle_email(user_id, email):

    generate_code = lambda length : str(random.randint(0, 10**length - 1)).zfill(length)

    token = None
    try:
        token = secrets.token_urlsafe(32)
        alt_code = generate_code(5)
        publish_event("user.verify_email", 
                      {"userID" : user_id, "email" : email, "token" : token, "code" : alt_code})

    except Exception as e: #TODO: make db table of emails to queue email sends?? or let unverified users to resend email??
        print(f"Error: failed to queue verification email: {e}")
        token = None

    if token != None:
        active_tokens.append({"user_id" : user_id, "token" : token, "code" : alt_code})
        print(f"active tokens now: {active_tokens}")

@public_bp.route("/login",methods = ["POST"])
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
        public_bp.logger.exception("login failed")
        message = RErrorMessage("Database error",503)

    return message.get()


@public_bp.route("/health")
def health():
    return RMessage().msg("status normal").get()


@public_bp.route("/verify", methods = ["GET"])
def verify_email():
    token = request.args.get("token", type=str)
    alt_code = request.args.get("code", type=str)

    if token == None and alt_code == None:
        return RErrorMessage("Missing token",400).get()

    entry = None

    print(f"active_tokens: {active_tokens}")

    for i,e in enumerate(active_tokens):
        if token == e["token"] or alt_code == e["code"]:
            entry = e
            break

    if entry == None:
        return RErrorMessage("Invalid token or code",400).get()

    user_id = entry["user_id"]

    message = RErrorMessage()

    try:
        with engine.begin() as conn:
            row = conn.execute(
                select(
                    users_table.c.id,
                    users_table.c.type,
                    users_table.c.status,
                       ).where(users_table.c.id == user_id)
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



            jwt_token = jwt.encode(
                    {
                        "sub": str(row.id),
                        "iss": JWT_ISSUER,
                        "id": row.id,
                        "type": row.type,
                        "status": "active",
                        },
                    JWT_SECRET,
                    algorithm="HS256",
                    )

        active_tokens.remove(entry)
        message = RMessage().msg("Email verified").add("token",jwt_token)

    except Exception:
        public_bp.logger.exception("verify_email failed")
        message = RErrorMessage("Database error",503)

    return message.get()
        


@public_bp.route("/register", methods=["POST"])
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
        _handle_email(new_id, email)

    
    return message.get()
