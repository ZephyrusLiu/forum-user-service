import uuid
import jwt

from flask import current_app, request, g
from werkzeug.exceptions import HTTPException
from sqlalchemy.exc import DBAPIError, IntegrityError

from utils.python.message import RErrorMessage

def register_error_handlers(app):
    #handles 404, 405, 413, abort
    @app.errorhandler(HTTPException)
    def handle_http_exception(e):
        return RErrorMessage(
            error_text=e.description,
            response_code=e.code
        ).get()


    # jwt
    @app.errorhandler(jwt.InvalidTokenError)
    def handle_jwt_invalid(e):
        return RErrorMessage("Invalid token", 401).get()

    #db
    @app.errorhandler(IntegrityError)
    def handle_integrity_error(e):
        current_app.logger.exception("Integrity error")
        return RErrorMessage(
            "Database constraint error",
            400
        ).get()

    @app.errorhandler(DBAPIError)
    def handle_db_error(e):
        current_app.logger.exception("Database error")
        return RErrorMessage(
            "Database error",
            503
        ).get()


    #others
    @app.errorhandler(KeyError)
    #NOTE: key errors are hard errors
    def handle_key_error(e):
        error_id = str(uuid.uuid4())

        current_app.logger.exception(
            "KeyError",
            extra={
                "error_id": error_id,
                "missing_key": e.args[0],
                "path": request.path,
                "method": request.method,
                "user": getattr(g, "user", None),
            },
        )

        if current_app.debug:
            return RErrorMessage(
                f"Internal error (KeyError): {e.args[0]}",
                500
            ).get()

        return RErrorMessage(
            "Internal server error",
            500
        ).get()


    @app.errorhandler(TypeError)
    def handle_type_error(e):
        current_app.logger.exception("TypeError")
        return RErrorMessage(
            "Invalid request data",
            400
        ).get()


    @app.errorhandler(ValueError)
    def handle_value_error(e):
        current_app.logger.exception("ValueError")
        return RErrorMessage(
            "Invalid value",
            400
        ).get()


    #catch all
    @app.errorhandler(Exception)
    def handle_unexpected_exception(e):
        error_id = str(uuid.uuid4())

        current_app.logger.exception(
            "Unhandled exception",
            extra={
                "error_id": error_id,
                "path": request.path,
                "method": request.method,
                "user": getattr(g, "user", None),
            },
        )

        if current_app.debug:
            return RErrorMessage(
                f"Internal error: {repr(e)}",
                500
            ).get()

        return RErrorMessage(
            "Internal server error",
            500
        ).get()

