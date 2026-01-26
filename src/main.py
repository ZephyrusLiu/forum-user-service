from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2].joinpath(".env"), override=True)
load_dotenv(Path(__file__).resolve().parents[1].joinpath(".env"), override=True)

import os
from flask import Flask
from .error_handler import register_error_handlers

#for debugging only
import code
#code.interact(local=locals())

from .routes.public import public_bp
from .routes.private import private_bp


app = Flask(__name__)

register_error_handlers(app)

app.config["JWT_SECRET"] = os.environ["JWT_SECRET"]
app.config["JWT_ISSUER"] = "forum_user_service"
app.config["JWT_ALG"] = "HS256"


app.config["DEFAULT_PROFILE_KEY"] = os.environ["DEFAULT_PROFILE_KEY"]

app.register_blueprint(public_bp)
app.register_blueprint(private_bp)


#PRIVATE

if __name__ == "__main__":
    app.run(port=5001, debug=True)



