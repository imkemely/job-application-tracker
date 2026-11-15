import os

import mysql.connector
from dotenv import load_dotenv

# connection settings live in .env so my password isn't on GitHub
load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "job_tracker"),
}


def get_db():
    return mysql.connector.connect(**DB_CONFIG)


def query(sql, params=None, one=False):
    # for SELECTs. returns a list of dicts, or just the first row if one=True
    conn = get_db()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(sql, params or ())
        rows = cursor.fetchall()
        cursor.close()
    finally:
        conn.close()

    if one:
        return rows[0] if rows else None
    return rows


def execute(sql, params=None):
    # for INSERT / UPDATE / DELETE. returns the new id after an INSERT
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute(sql, params or ())
        conn.commit()
        new_id = cursor.lastrowid
        cursor.close()
    finally:
        conn.close()
    return new_id
