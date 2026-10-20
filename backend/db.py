"""
StockSense — Database connection helper.
Uses environment variables with sensible defaults for local dev.
"""

import os
import psycopg2
import psycopg2.extras


def get_conn():
    """Return a new psycopg2 connection using env vars or defaults."""
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME", "stocksense"),
        user=os.getenv("DB_USER", "stocksense"),
        password=os.getenv("DB_PASS", "stocksense123"),
    )
