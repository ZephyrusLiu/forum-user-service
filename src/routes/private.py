from flask import request, Blueprint, current_app, g
from sqlalchemy import select, insert, update, bindparam
from sqlalchemy.exc import IntegrityError, DBAPIError
from werkzeug.security import generate_password_hash

from ..user_db import engine, users_table, media_table
from .common import get_jwt_token, handle_email
from utils.python.message import RMessage, RErrorMessage, RResponse
from utils.python.auth import login_required

private_bp = Blueprint("private",__name__,url_prefix= "/users/")

from enum import Enum

class Role(Enum):
    Self = 0
    Admin = 1
    Super = 2
    NA = -1


def _get_role(user, other_id):
    role = user["role"]
    user_id = int(user["userId"])

    match role:
        case "admin": return Role.Admin
        case "super": return Role.Super
        case _: return Role.Self if other_id == user_id else Role.NA


def _is_barred(role, field):

    barred = {
            Role.Self : ["type", "status"],
            Role.Admin : ["email", "passHash","type"],
            Role.Super : ["email", "passHash"]
            }

    return field in barred[role]



@private_bp.route("/ping",methods = ["GET"])
@login_required
def ping():
    return RMessage().msg("pong").get()



@private_bp.route("/reverify",methods = ["POST"])
@login_required
def reverify():
    data = request.get_json()

    if not data:
        return RErrorMessage("Missing JSON body",400).get()

    try:
        user_id = int(g.user["userId"])

        stmt = select(
            users_table.c.email,
            users_table.c.status
        ).where(users_table.c.id == user_id)

        with engine.begin() as conn:
            user = conn.execute(stmt).mappings().first()

            if not user:
                return RErrorMessage("User not found", 404).get()

            if user["status"] != "unverified":
                return RErrorMessage("User already verified", 400).get()

            email = user["email"]

        handle_email(user_id, email)

        return RResponse().add("message", "Verification email resent").get()

    except DBAPIError:
        return RErrorMessage("Database error", 503).get()

@private_bp.route("/<int:user_id>/profile",methods = ["GET"])
@login_required
def get_profile(user_id):

    message = RErrorMessage()

    stmt_user = select(
        users_table.c.id,
        users_table.c.firstName,
        users_table.c.lastName,
        users_table.c.joinDate,
        users_table.c.type,
        users_table.c.status,
        users_table.c.profileMediaID
    ).where(users_table.c.id == user_id)

    stmt_media = select(
        media_table.c.s3Key
    ).where(media_table.c.id == bindparam("media_id"))

    try:
        with engine.begin() as conn:
            user = conn.execute(stmt_user).mappings().first() 

            if not user:
                return RErrorMessage("User not found",404).get()


            profile_media = current_app.config["DEFAULT_PROFILE_KEY"]

            if user["profileMediaID"] is not None:
                m = conn.execute(
                        stmt_media,
                        {"media_id": user["profileMediaID"]}
                         ).mappings().first()

                if m:
                    profile_media = m["s3Key"]

            message = RResponse().add("id",user["id"]).\
            add("firstName",user["firstName"]).\
            add("lastName",user["lastName"]).\
            add("joinDate",user["joinDate"].isoformat()).\
            add("type",user["type"]).\
            add("status",user["status"]).\
            add("profileMedia",profile_media)

    except DBAPIError:
        message = RErrorMessage("Database error",503)

    return message.get()


@private_bp.route("/<int:user_id>/profile", methods=["PATCH"])
@login_required
def update_user(user_id):

    data = request.get_json()
    if data is None:
        return RErrorMessage("Missing json body", 400).get()



    role = _get_role(g.user, user_id)
    if role == Role.NA:
        return RErrorMessage(
            "You do not have authorization to make this change", 403
        ).get()

    password = data.get("password")

    update_fields = {
        "firstName": data.get("firstName"),
        "lastName": data.get("lastName"),
        "email": data.get("email"),
        "type": data.get("type"),
        "status": data.get("status"),
        "passHash": generate_password_hash(password) if password is not None else None,
    }

    s3Key = None

    if "s3Key" in update_fields:
        s3Key = update_fields["s3Key"]
        del update_fields["s3Key"]

    updates = {k: v for k, v in update_fields.items() if v is not None}

    if not updates:
        return RErrorMessage("No valid update fields found", 400).get()

    for field in updates:
        if _is_barred(role, field):
            return RErrorMessage(
                "You do not have authorization to make this change", 403
            ).get()


    #NOTE: this MUST happen here afer all barring checks
    to_send_email = role == Role.Self and "email" in updates 
    if to_send_email:
        updates["status"] = "unverified"

    try:
        with engine.begin() as conn:

            if s3Key != None:
                stmt = insert(media_table).values(userID= user_id, s3Key=se3Key)
                result = conn.execute(stmt)
                media_id = result. inserted_primary_key[0]

                updates["profileMediaID"] = media_id



            if "status" in updates and role == Role.Admin:
                target = conn.execute(
                    select(users_table.c.type)
                    .where(users_table.c.id == user_id)
                ).first()

                if not target:
                    return RErrorMessage("User not found", 404).get()

                if target.type != "user":
                    return RErrorMessage(
                        "You do not have authorization to make this change", 403
                    ).get()

            

            result = conn.execute(
                update(users_table)
                .where(users_table.c.id == user_id)
                .values(**updates)
            )

            if result.rowcount != 1:
                return RErrorMessage("User not found", 404).get()


            message = RMessage()

            if to_send_email:
                message.add("token",get_jwt_token())
                handle_email(user_id, updates["email"])

        return message.msg("User updated").get()

    except DBAPIError:
        return RErrorMessage("Database error", 503).get()

