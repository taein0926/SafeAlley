from typing import TypedDict

import psycopg
from psycopg import sql

from app.core.config import get_settings


class DatabaseStatus(TypedDict):
    status: str
    name: str
    postgis_version: str


class DatabaseConnectionError(RuntimeError):
    """Raised when the database or PostGIS health query fails."""


def connect_database() -> psycopg.Connection:
    settings = get_settings()
    return psycopg.connect(
        host=settings.db_host,
        port=settings.db_port,
        dbname=settings.postgres_db,
        user=settings.postgres_user,
        password=settings.postgres_password,
        connect_timeout=settings.db_connect_timeout_seconds,
    )


def check_database() -> DatabaseStatus:
    try:
        with connect_database() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    sql.SQL("SELECT current_database(), PostGIS_Version()")
                )
                row = cursor.fetchone()
    except psycopg.Error as exc:
        raise DatabaseConnectionError("PostgreSQL/PostGIS connection failed") from exc

    if row is None:
        raise DatabaseConnectionError("PostgreSQL/PostGIS health query returned no row")

    database_name, postgis_version = row
    return {
        "status": "ok",
        "name": str(database_name),
        "postgis_version": str(postgis_version),
    }
