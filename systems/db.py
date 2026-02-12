from os import getenv
from peewee import Proxy, DoesNotExist
from playhouse.db_url import connect

db = Proxy()

def proxy_load():
    try:
        db_uri = getenv("PGDB_CONNECTION") or "sqlite:///local.db"
        real_db = connect(db_uri)
        db.initialize(real_db)
    except Exception as e:
        print("[- ERROR -] Failed to change proxy to :", e)
        return False
    return True

DoesNotExist = DoesNotExist