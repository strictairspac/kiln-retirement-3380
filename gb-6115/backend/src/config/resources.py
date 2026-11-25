from redis import Redis
from sqlalchemy import create_engine, event

from .settings import DATABASE_URL, REDIS_URL

engine = create_engine(DATABASE_URL, pool_pre_ping=True)

if engine.dialect.name == "sqlite":
    # SQLite 无行锁，并发写事务等待锁而不是立即报 database is locked。
    @event.listens_for(engine, "connect")
    def _sqlite_busy_timeout(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA busy_timeout = 5000")
        cursor.close()

cache = Redis.from_url(REDIS_URL, socket_connect_timeout=2, socket_timeout=3)
