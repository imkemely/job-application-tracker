"""Database helpers for the Job Application Tracker.

Connection settings come from a .env file (see .env.example) so that
nobody's MySQL password gets committed to GitHub.
"""
import os

import mysql.connector
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "job_tracker"),
}


def get_db():
    """Open a new connection to the job_tracker database."""
    return mysql.connector.connect(**DB_CONFIG)


def query(sql, params=None, one=False):
    """Run a SELECT and return rows as dictionaries.

    With one=True, return just the first row (or None if there isn't one).
    """
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
    """Run an INSERT, UPDATE or DELETE and commit it.

    Returns the new row's id for inserts (0 for updates/deletes).
    """
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
