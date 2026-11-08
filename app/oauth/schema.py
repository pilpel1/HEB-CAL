"""טבלאות OAuth. DDL אידמפוטנטי, בלי העלאת user_version."""
from __future__ import annotations

import sqlite3


def ensure_oauth_schema(db) -> None:
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS oauth_clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id TEXT NOT NULL UNIQUE,
            secret_hash TEXT,
            name TEXT NOT NULL,
            redirect_uris TEXT NOT NULL,
            created_at TEXT NOT NULL,
            revoked_at TEXT
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS oauth_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code_hash TEXT NOT NULL UNIQUE,
            client_id TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            resource TEXT NOT NULL,
            issuer TEXT NOT NULL,
            redirect_uri TEXT NOT NULL,
            scopes TEXT NOT NULL,
            code_challenge TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            consumed_at TEXT,
            grant_family TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS oauth_grants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            family_id TEXT NOT NULL,
            client_id TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            resource TEXT NOT NULL,
            issuer TEXT NOT NULL,
            scopes TEXT NOT NULL,
            access_hash TEXT UNIQUE,
            refresh_hash TEXT UNIQUE,
            previous_refresh_hash TEXT,
            access_expires_at TEXT,
            refresh_expires_at TEXT,
            last_used_at TEXT,
            revoked_at TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    db.execute("CREATE INDEX IF NOT EXISTS idx_oauth_grants_family ON oauth_grants(family_id)")
    try:
        db.execute("ALTER TABLE oauth_grants ADD COLUMN previous_refresh_hash TEXT")
    except sqlite3.OperationalError:
        pass
    db.execute("CREATE INDEX IF NOT EXISTS idx_oauth_grants_user ON oauth_grants(user_id)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_oauth_codes_hash ON oauth_codes(code_hash)")
    db.commit()
