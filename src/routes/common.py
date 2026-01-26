import jwt
import secrets
import random
from flask import current_app
from ..rmq import publish_event


def get_jwt_token(user_id, user_type, user_status):
    JWT_SECRET = current_app.config["JWT_SECRET"]
    JWT_ISSUER = current_app.config["JWT_ISSUER"]
    JWT_ALG = current_app.config["JWT_ALG"]

    token = jwt.encode(
            {
                "sub": str(user_id),
                "iss": JWT_ISSUER,

                "id": user_id,
                "type": user_type,
                "status": user_status,
        
                },
            JWT_SECRET,
            algorithm=JWT_ALG
            ) 

    return token

active_tokens = [] #TODO: expire tokens after 15 minutes

def handle_email(user_id, email):
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
