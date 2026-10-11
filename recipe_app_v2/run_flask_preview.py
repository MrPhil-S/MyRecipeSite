"""Launch unchanged legacy Flask on loopback, dev-only and read-only for checks.

Use the legacy MyRecipesVenv interpreter. No imports of the new dependencies.
"""
import configparser
import socket
from pathlib import Path
import sys

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
config = configparser.ConfigParser(interpolation=None)
config.read(root / "config.ini")
from sqlalchemy.engine import make_url

url = make_url(config["dev"]["db_uri"])
if socket.gethostname() == "raspberrypi" or (
    url.drivername != "mysql+pymysql" or url.database != "MyRecipes_DEV"
    or url.host != "192.168.1.14" or url.port != 3307 or url.query
):
    raise RuntimeError("Legacy preview requires the dev database on this PC.")

from myrecipes import app, db
from sqlalchemy import event

with app.app_context():
    @event.listens_for(db.engine, "connect")
    def readonly(dbapi_connection, connection_record):
        with dbapi_connection.cursor() as cursor:
            cursor.execute("SET SESSION TRANSACTION READ ONLY")

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8080, debug=False, use_reloader=False)
