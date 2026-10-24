import configparser
from functools import lru_cache
import os
from pathlib import Path

from sqlalchemy.engine import URL, make_url

ROOT = Path(__file__).resolve().parent.parent


def app_environment() -> str:
    value = os.environ.get("RECIPE_APP_ENV", "dev")
    if value not in ("dev", "production"):
        raise RuntimeError("RECIPE_APP_ENV must be dev or production.")
    return value


@lru_cache(maxsize=8)
def dev_database_url(config_path=None) -> URL:
    configured_url = os.environ.get("RECIPE_DEV_DB_URI")
    if not configured_url:
        path = Path(config_path or os.environ.get("RECIPE_CONFIG", ROOT / "config.ini"))
        config = configparser.ConfigParser(interpolation=None)
        if not config.read(path) or not config.has_option("dev", "db_uri"):
            raise RuntimeError("RECIPE_DEV_DB_URI or a config.ini containing [dev] db_uri is required.")
        configured_url = config["dev"]["db_uri"]
    try:
        url = make_url(configured_url)
    except Exception:
        raise RuntimeError("Invalid [dev] database URL; check config.ini.") from None
    if (url.drivername != "mysql+pymysql" or url.database != "MyRecipes_DEV"
            or url.host != "192.168.1.14" or url.port != 3307 or url.query):
        raise RuntimeError("Only mysql+pymysql at 192.168.1.14:3307/MyRecipes_DEV is allowed.")
    return url


@lru_cache(maxsize=8)
def production_database_url(config_path=None) -> URL:
    configured_url = os.environ.get("RECIPE_PROD_DB_URI")
    if not configured_url:
        path = Path(config_path or os.environ.get("RECIPE_CONFIG", ROOT / "config.ini"))
        config = configparser.ConfigParser(interpolation=None)
        if not config.read(path) or not config.has_option("prod", "db_uri"):
            raise RuntimeError("RECIPE_PROD_DB_URI or a config.ini containing [prod] db_uri is required.")
        configured_url = config["prod"]["db_uri"]
    try:
        url = make_url(configured_url)
    except Exception:
        raise RuntimeError("Invalid production database URL.") from None
    if (url.drivername != "mysql+pymysql" or url.database != "MyRecipes"
            or url.host != "192.168.1.14" or url.port != 3307 or url.query):
        raise RuntimeError("Only the configured MyRecipes production database is allowed.")
    return url


def database_url() -> URL:
    if app_environment() == "production":
        if os.environ.get("RECIPE_DEV_DB_URI") or os.environ.get("RECIPE_DEV_WRITES") == "1":
            raise RuntimeError("Development database settings cannot be used in production.")
        return production_database_url()
    if os.environ.get("RECIPE_PROD_DB_URI") or os.environ.get("RECIPE_PROD_WRITES") == "1":
        raise RuntimeError("Production database settings cannot be used in development.")
    return dev_database_url()
