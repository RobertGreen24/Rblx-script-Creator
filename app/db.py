"""SQLite storage layer (stdlib only - no ORM required).

Two tables back the site:

* ``projects`` - scripts saved from the editor or the feature builder
* ``snippets`` - the copy/paste snippet catalogue (seeded, plus user additions)
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

import click
from flask import current_app, g

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT    NOT NULL,
    description  TEXT    NOT NULL DEFAULT '',
    script_type  TEXT    NOT NULL DEFAULT 'server',
    source       TEXT    NOT NULL DEFAULT 'editor',
    config       TEXT    NOT NULL DEFAULT '{}',
    code         TEXT    NOT NULL DEFAULT '',
    starred      INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT    NOT NULL,
    updated_at   TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS snippets (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    title        TEXT    NOT NULL,
    category     TEXT    NOT NULL DEFAULT 'Basics',
    summary      TEXT    NOT NULL DEFAULT '',
    code         TEXT    NOT NULL,
    tags         TEXT    NOT NULL DEFAULT '',
    script_type  TEXT    NOT NULL DEFAULT 'server',
    builtin      INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_projects_updated ON projects(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_snippets_category ON snippets(category);
"""


def utcnow() -> str:
    """ISO-8601 UTC timestamp (seconds resolution)."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def get_db() -> sqlite3.Connection:
    """Return the request-scoped database connection."""
    if "db" not in g:
        g.db = sqlite3.connect(
            current_app.config["DATABASE"],
            detect_types=sqlite3.PARSE_DECLTYPES,
            timeout=15,
        )
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
        g.db.execute("PRAGMA journal_mode = WAL")
    return g.db


def close_db(_exception=None) -> None:
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_db() -> None:
    """Create tables and seed the built-in snippet catalogue."""
    conn = get_db()
    conn.executescript(SCHEMA)
    conn.commit()
    _seed_snippets(conn)
    _seed_projects(conn)


def _seed_snippets(conn: sqlite3.Connection) -> None:
    from .snippets import SNIPPETS

    known = {
        row["title"] for row in conn.execute("SELECT title FROM snippets WHERE builtin = 1")
    }
    added = 0
    for snippet in SNIPPETS:
        if snippet["title"] in known:
            continue
        conn.execute(
            """INSERT INTO snippets
               (title, category, summary, code, tags, script_type, builtin, created_at)
               VALUES (?, ?, ?, ?, ?, ?, 1, ?)""",
            (
                snippet["title"],
                snippet["category"],
                snippet["summary"],
                snippet["code"],
                ",".join(snippet.get("tags", [])),
                snippet.get("script_type", "server"),
                utcnow(),
            ),
        )
        added += 1
    if added:
        conn.commit()


def _seed_projects(conn: sqlite3.Connection) -> None:
    """Give a brand new install a couple of example projects to poke at."""
    if conn.execute("SELECT COUNT(*) AS n FROM projects").fetchone()["n"]:
        return

    from .features import ALL_FEATURES, build_scripts

    sample = [f for f in ALL_FEATURES if f.id in ("sprint", "coin_collect", "leaderstats")]
    config = {"features": [{"id": f.id, "params": f.default_params()} for f in sample]}
    scripts = build_scripts(config)

    now = utcnow()
    for script in scripts[:2]:
        conn.execute(
            """INSERT INTO projects
               (name, description, script_type, source, config, code, created_at, updated_at)
               VALUES (?, ?, ?, 'builder', ?, ?, ?, ?)""",
            (
                f"Example - {script['name']}",
                "Auto-generated starter sample. Edit it or delete it - it is yours now.",
                script["script_type"],
                json.dumps(config),
                script["code"],
                now,
                now,
            ),
        )
    conn.commit()


def register(app) -> None:
    app.teardown_appcontext(close_db)

    @app.cli.command("init-db")
    def init_db_command():
        """Create the database tables and seed built-in content."""
        init_db()
        click.echo("Initialised the database.")


init_app = register
