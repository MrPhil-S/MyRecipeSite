import configparser
import os
from pathlib import Path

from sqlalchemy.engine import URL, make_url

ROOT = Path(__file__).resolve().parent.parent


def dev_database_url(config_path=None) -> URL:
    path = Path(config_path or os.environ.get("RECIPE_CONFIG", ROOT / "config.ini"))
    config = configparser.ConfigParser(interpolation=None)
    if not config.read(path) or not config.has_option("dev", "db_uri"):
        raise RuntimeError("A config.ini containing [dev] db_uri is required.")
    try:
        url = make_url(config["dev"]["db_uri"])
    except Exception:
        raise RuntimeError("Invalid [dev] database URL; check config.ini.") from None
    if (url.drivername != "mysql+pymysql" or url.database != "MyRecipes_DEV"
            or url.host != "192.168.1.14" or url.port != 3307 or url.query):
        raise RuntimeError("Only mysql+pymysql at 192.168.1.14:3307/MyRecipes_DEV is allowed.")
    return url
