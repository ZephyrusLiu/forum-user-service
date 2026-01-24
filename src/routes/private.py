from flask import request, Blueprint
from sqlalchemy import select, insert, update, bindparam
from sqlalchemy.exc import IntegrityError, DBAPIError
from werkzeug.security import generate_password_hash

from ..user_db import engine, users_table, media_table
from utils.python.message import RMessage, RErrorMessage, RResponse
from utils.python.auth import login_required
from .public import _handle_email, JWT_SECRET, JWT_ISSUER

private_bp = Blueprint("private",__name__,url_prefix= "/users/")

from enum import Enum

class Role(Enum):
    Self = 0
    Admin = 1
    Super = 2
    NA = -1


def _get_role(token_info, other_id):
    role = token_info.user["role"]
    user_id = token_info.user["userId"]

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
def ping():
    return RMessage().msg("pong").get()


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
        media_table.c.s3Bucket,
        media_table.c.s3Key
    ).where(media_table.c.id == bindparam("media_id"))

    try:
        with engine.begin() as conn:
            user = conn.execute(stmt_user).mprivate_bp.ngs().first()

            if not user:
                return RErrorMessage("User not found",404).get()

            profile_media = None
            if user["profileMediaID"] is not None:
                m = conn.execute(
                    stmt_media,
                    {"media_id": user["profileMediaID"]}
                ).mprivate_bp.ngs().first()

                if m:
                    profile_media = {
                        "s3Bucket": m["s3Bucket"],
                        "s3Key": m["s3Key"]
                    }

        return RResponse().add("id",user["id"]).\
                add("firstName",user["firstName"]).\
                add("lastName",user["lastName"]).\
                add("joinDate",user["joinDate"].isoformat()).\
                add("type",user["type"]).\
                add("status",user["status"]).\
                add("profileMediaID",user["profileMediaID"]).\
                add("profileMedia",profile_media).get()

    except DBAPIError:
        message = RErrorMessage("Database error",503)

    return message.get()


@private_bp.route("/<int:user_id>/profile", methods=["PATCH"])
@login_required
def update_user(user_id):

    data = request.get_json()
    if data is None:
        return RErrorMessage("Missing json body", 400).get()

    role = _get_role(g, user_id)
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
        # "profile_url": data.get("profileURL"),
    }

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
                token = jwt_token.encode(
                        {
                            "sub": str(user_id),
                            "iss": JWT_ISSUER,
                            "id": user_id,
                            "type": g.user["role"],
                            "status": "unverified",
                            },
                        JWT_SECRET,
                        algorithm="HS256",
                        )

                message.add("token",token)
                _handle_email(user_id, updates["email"])

        return message.msg("User updated").get()

    except DBAPIError:
        return RErrorMessage("Database error", 503).get()

