from flask import request, Blueprint, current_app
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import select, insert, update, bindparam
from sqlalchemy.exc import IntegrityError, DBAPIError

from ..user_db import engine, users_table, media_table
from .common import get_jwt_token, handle_email
from ..rmq import get_rmq_channel, publish_event
from utils.python.message import RMessage, RErrorMessage, RResponse


public_bp = Blueprint("public",__name__,url_prefix= "/users/")

active_tokens = [] #TODO: expire tokens after 15 minutes



@public_bp.route("/login",methods = ["POST"])
def login():
    data = request.get_json()
    if not data:
        return RErrorMessage("Missing JSON body", 400).get()

    email = data["email"]
    passw = data["password"]

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
            return RErrorMessage("Invalid credentials", 401).get()

        if row.status == "banned":
            return RErrorMessage("Account banned", 403).get()

        if not check_password_hash(row.passHash, passw):
            return RErrorMessage("Invalid credentials", 401).get()

        return RMessage().add("token",
                              get_jwt_token(row.id, row.type, row.status)).get()


@public_bp.route("/health")
def health():
    return RMessage().msg("status normal").get()


@public_bp.route("/verify", methods = ["GET"])
def verify_email():
    token = request.args.get("token", type=str)
    alt_code = request.args.get("code", type=str)

    if token is None and alt_code is None:
        return RErrorMessage("Missing token", 400).get()

    entry = None
    for e in active_tokens:
        if token == e["token"] or alt_code == e["code"]:
            entry = e
            break

    if entry is None:
        return RErrorMessage("Invalid token or code", 400).get()

    user_id = entry["user_id"]
    user_type = "unverified"

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
            return RErrorMessage("User not found", 404).get()

        user_type = row.type

        result = conn.execute(
            update(users_table)
            .where(users_table.c.id == user_id)
            .values(status="active")
        )

        if result.rowcount != 1:
            return RErrorMessage("Verification failed", 500).get()

    active_tokens.remove(entry)

    return RMessage().msg("Email verified").add("token",get_jwt_token(user_id, user_type, "active")).get()
        


@public_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json()

    firstName = data["firstName"]
    lastName = data["lastName"]
    email = data["email"]
    passw = data["password"]
    passHash = generate_password_hash(passw)

    stmt = insert(users_table).values(
        firstName=firstName,
        lastName=lastName,
        email=email,
        passHash=passHash,
    )

    new_id = None

    try:
        with engine.begin() as conn:
            result = conn.execute(stmt)
            new_id = result.inserted_primary_key[0]
            message = RMessage(201).msg("New user registered").add("id", new_id)
    except IntegrityError as e:
        error_code = e.orig.args[0] if getattr(e, "orig", None) and getattr(e.orig, "args", None) else None
        text, code = ("Email already registered", 409) if error_code == 1062 else ("Database constraint error", 400)
        message = RErrorMessage(text, code)

    if new_id is not None:
        handle_email(new_id, email)

    return message.get()
