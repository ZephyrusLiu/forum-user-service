from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2].joinpath(".env"), override=True)
load_dotenv(Path(__file__).resolve().parents[1].joinpath(".env"), override=True)

from flask import Flask

#for debugging only
import code
#code.interact(local=locals())

from .routes.public import public_bp
from .routes.private import private_bp


app = Flask(__name__)

app.register_blueprint(public_bp)
app.register_blueprint(private_bp)


#PRIVATE

if __name__ == "__main__":
    app.run(port=5001, debug=True)



