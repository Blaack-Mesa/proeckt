"""Единая база данных (SQLite): таблицы users, projects, tasks, reports."""
import sqlite3

from flask import current_app, g

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT    NOT NULL UNIQUE,
    full_name     TEXT    NOT NULL,
    password_hash TEXT    NOT NULL,
    role          TEXT    NOT NULL CHECK (role IN ('admin', 'manager', 'executor')),
    is_active     INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    description TEXT    NOT NULL DEFAULT '',
    owner_id    INTEGER NOT NULL REFERENCES users(id),
    created_at  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    title       TEXT    NOT NULL,
    description TEXT    NOT NULL DEFAULT '',
    status      TEXT    NOT NULL DEFAULT 'new'
                CHECK (status IN ('new', 'in_progress', 'review', 'done', 'rejected')),
    assignee_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    creator_id  INTEGER NOT NULL REFERENCES users(id),
    due_date    TEXT,
    created_at  TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS reports (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    report_type TEXT    NOT NULL CHECK (report_type IN ('assignee', 'project', 'period')),
    params      TEXT    NOT NULL,
    rows_count  INTEGER NOT NULL,
    created_by  INTEGER NOT NULL REFERENCES users(id),
    created_at  TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tasks_project  ON tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_tasks_assignee ON tasks(assignee_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status   ON tasks(status);
"""


def get_db() -> sqlite3.Connection:
    """Соединение с БД, одно на запрос (хранится в flask.g)."""
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_exc=None) -> None:
    """Закрывает соединение в конце запроса."""
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_db() -> None:
    """Создаёт таблицы, если их ещё нет."""
    get_db().executescript(SCHEMA)
    get_db().commit()
