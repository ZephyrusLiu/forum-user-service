from flask import request, Blueprint
from sqlalchemy import select, insert, update, bindparam
from sqlalchemy.exc import IntegrityError, DBAPIError

from ..user_db import engine, users_table, media_table
from utils.python.message import RMessage, RErrorMessage, RResponse

private_bp = Blueprint("private",__name__,url_prefix= "/users/")


@private_bp.route("/ping",methods = ["GET"])
def ping():
    return RMessage().msg("pong").get()


@private_bp.route("/<int:user_id>/profile",methods = ["GET"])
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

@private_bp.route("/<int:user_id>/profile", methods=["PUT"])
def update_profile(user_id):
    data = request.get_json()
    if not data or "profileMediaID" not in data:
        return RErrorMessage("Missing profileMediaID", 400).get()

    media_id = data["profileMediaID"]

    try:
        with engine.begin() as conn:
            user = conn.execute(
                select(users_table.c.id)
                .where(users_table.c.id == user_id)
            ).first()

            if not user:
                return RErrorMessage("User not found", 404).get()

            media = conn.execute(
                select(media_table.c.id)
                .where(
                    media_table.c.id == media_id,
                    media_table.c.userID == user_id
                )
            ).first()

            if not media:
                return RErrorMessage("Invalid profile media", 400).get()

            conn.execute(
                update(users_table)
                .where(users_table.c.id == user_id)
                .values(profileMediaID=media_id)
            )

        return RMessage().info("Profile updated").get()

    except DBAPIError:
        return RErrorMessage("Database error", 503).get()
