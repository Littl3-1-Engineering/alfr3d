import os
import logging
from dbutils.pooled_db import PooledDB
import pymysql

logger = logging.getLogger(__name__)

MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE", "localhost")
MYSQL_USER = os.environ.get("MYSQL_USER", "root")
MYSQL_PSWD = os.environ.get("MYSQL_PSWD", "")
MYSQL_DB = os.environ.get("MYSQL_NAME", "alfr3d_db")

_pool = None


def get_pool():
    global _pool
    if _pool is None:
        try:
            logger.info(
                f"Creating db pool (host={MYSQL_DATABASE}, user={MYSQL_USER}, db={MYSQL_DB})"
            )
            _pool = PooledDB(
                creator=pymysql,
                maxconnections=20,
                mincached=5,
                maxcached=10,
                blocking=True,
                host=MYSQL_DATABASE,
                user=MYSQL_USER,
                password=MYSQL_PSWD,
                database=MYSQL_DB,
                charset="utf8mb4",
            )
            logger.info("Database connection pool created successfully")
        except Exception as e:
            logger.error(f"Failed to create database connection pool: {e}")
            raise
    return _pool


def get_connection():
    pool = get_pool()
    return pool.connection()


def close_pool():
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None
        logger.info("Database connection pool closed")
