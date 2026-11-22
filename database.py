import json
import os
import re
import sqlite3
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tank_bot.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    name TEXT,
    role INTEGER DEFAULT 0,
    admin_level INTEGER DEFAULT 0,
    pos TEXT,
    status TEXT DEFAULT 'newbie',
    points REAL DEFAULT 0,
    banned INTEGER DEFAULT 0,
    ban_src TEXT,
    timezone TEXT DEFAULT 'Europe/Moscow',
    rights TEXT,
    created_at TEXT,
    leave_at TEXT
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT,
    aid TEXT,
    pos TEXT,
    src TEXT,
    status TEXT DEFAULT 'active',
    done_at TEXT,
    final TEXT,
    note_msg INTEGER,
    created_at TEXT,
    closed_by INTEGER,
    created_by INTEGER,
    closers TEXT,
    deleted_at TEXT,
    deadline TEXT,
    template_id INTEGER
);
CREATE TABLE IF NOT EXISTS checklists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,
    status TEXT DEFAULT 'active',
    created_by INTEGER,
    deadline TEXT,
    bonus REAL DEFAULT 2
);
CREATE TABLE IF NOT EXISTS checklist_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    checklist_id INTEGER,
    text TEXT,
    assigned_to INTEGER,
    status TEXT DEFAULT 'free',
    taker_id INTEGER,
    taken_mode TEXT,
    proof_text TEXT,
    proof_files TEXT,
    checked_by INTEGER,
    checked_at TEXT,
    check_result TEXT,
    check_comment TEXT
);
CREATE TABLE IF NOT EXISTS checklist_assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    checklist_id INTEGER,
    user_id INTEGER
);
CREATE TABLE IF NOT EXISTS works (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER,
    user_id INTEGER,
    kind TEXT,
    parent_id INTEGER,
    text TEXT,
    files TEXT,
    form_id INTEGER,
    answers TEXT,
    status TEXT DEFAULT 'submitted',
    grade INTEGER,
    result TEXT,
    comment TEXT,
    comment_photo TEXT,
    points REAL DEFAULT 0,
    reviewer_id INTEGER,
    best INTEGER DEFAULT 0,
    created_at TEXT,
    reviewed_at TEXT
);
CREATE TABLE IF NOT EXISTS punishments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    kind TEXT,
    topic TEXT,
    data TEXT,
    deadline TEXT,
    status TEXT DEFAULT 'active',
    assigned_by INTEGER,
    created_at TEXT,
    submitted_at TEXT,
    result_text TEXT,
    result_photo TEXT,
    checked_by INTEGER,
    check_comment TEXT,
    fined_days INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS votes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT,
    target_id INTEGER,
    status TEXT DEFAULT 'active',
    deadline TEXT,
    reason TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS vote_records (
    vote_id INTEGER,
    voter_id INTEGER,
    weight INTEGER,
    choice TEXT,
    PRIMARY KEY (vote_id, voter_id)
);
CREATE TABLE IF NOT EXISTS trash (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name TEXT,
    row_id INTEGER,
    deleted_at TEXT,
    data TEXT
);
CREATE TABLE IF NOT EXISTS archive (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name TEXT,
    row_id INTEGER,
    archived_at TEXT,
    data TEXT
);
CREATE TABLE IF NOT EXISTS materials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT,
    title TEXT,
    text TEXT,
    file_id TEXT,
    url TEXT,
    pinned INTEGER DEFAULT 0,
    visible TEXT,
    created_by INTEGER,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT,
    kind TEXT,
    weekly TEXT,
    dates TEXT,
    time TEXT,
    fired INTEGER DEFAULT 0,
    chat_id INTEGER,
    thread INTEGER,
    active INTEGER DEFAULT 1,
    created_by INTEGER,
    dm_users TEXT,
    created_at TEXT,
    photo TEXT
);
CREATE TABLE IF NOT EXISTS templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,
    text TEXT,
    pos TEXT,
    photo TEXT,
    created_at TEXT,
    created_by INTEGER
);
CREATE TABLE IF NOT EXISTS groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER,
    thread_id INTEGER,
    type TEXT,
    is_permanent INTEGER DEFAULT 1,
    title TEXT
);
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    action TEXT,
    details TEXT,
    ts TEXT
);
CREATE TABLE IF NOT EXISTS curators (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    pos TEXT
);
CREATE TABLE IF NOT EXISTS forms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,
    fields TEXT,
    created_by INTEGER,
    created_at TEXT
);
"""


INT_COLUMNS = {
    "id", "role", "admin_level", "banned", "note_msg", "closed_by", "created_by",
    "reviewer_id", "checked_by", "assigned_by", "checklist_id", "assigned_to",
    "taker_id", "target_id", "vote_id", "voter_id", "chat_id", "thread", "thread_id",
    "parent_id", "form_id", "template_id", "row_id", "user_id", "task_id",
    "fired", "active", "pinned", "is_permanent", "weight", "best", "grade",
}
FLOAT_COLUMNS = {"points", "bonus"}


def _row_factory(cursor, row):
    out = {}
    for col, value in zip(cursor.description, row):
        key = col[0]
        if isinstance(value, str):
            s = value.strip()
            if key in INT_COLUMNS and re.fullmatch(r"-?\d+", s):
                value = int(s)
            elif key in FLOAT_COLUMNS and re.fullmatch(r"-?\d+(\.\d+)?", s):
                value = float(s)
        out[key] = value
    return out


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = _row_factory
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _schema_columns():
    result = {}
    for chunk in SCHEMA.split("CREATE TABLE IF NOT EXISTS")[1:]:
        head, _, body = chunk.partition("(")
        table = head.strip()
        if not table.isidentifier():
            continue
        body = body.split(");")[0]
        cols = []
        for line in body.splitlines():
            line = line.strip().rstrip(",")
            if not line or line.upper().startswith(("PRIMARY KEY", "UNIQUE", "FOREIGN", "CHECK")):
                continue
            name, _, decl = line.partition(" ")
            if name and decl and "PRIMARY KEY" not in decl.upper():
                cols.append((name, decl))
        result[table] = cols
    return result


def _migrate(conn):
    for table, cols in _schema_columns().items():
        existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        if not existing:
            continue
        for name, decl in cols:
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
    conn.commit()


def init_db():
    conn = _conn()
    conn.executescript(SCHEMA)
    conn.commit()
    _migrate(conn)
    conn.close()


def query(sql, params=()):
    conn = _conn()
    rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    conn.close()
    return rows


def get(sql, params=()):
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql, params=()):
    conn = _conn()
    cur = conn.execute(sql, params)
    conn.commit()
    rid = cur.lastrowid
    conn.close()
    return rid


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def setting(key, default=None):
    row = get("SELECT value FROM settings WHERE key=?", (key,))
    if row is None:
        return default
    return row["value"]


def set_setting(key, value):
    execute(
        "INSERT INTO settings(key,value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, str(value)),
    )


def get_user(uid):
    return get("SELECT * FROM users WHERE id=?", (uid,))


def is_admin(u):
    return u and u["role"] >= 1


def is_owner(u):
    return u and u["role"] >= 4


def rights_of(u):
    if not u:
        return []
    if u["role"] >= 4:
        return [r[0] for r in RIGHTS_ALL]
    raw = u.get("rights")
    if raw:
        return json.loads(raw)
    return []


from config import RIGHTS  # noqa: E402
RIGHTS_ALL = RIGHTS


def has_right(u, right):
    if not u:
        return False
    if u["role"] >= 4:
        return True
    return right in rights_of(u)


def log_action(uid, action, details=""):
    execute(
        "INSERT INTO logs(user_id,action,details,ts) VALUES(?,?,?,?)",
        (uid, action, details, now()),
    )


def log_system(action, details=""):
    log_action(0, action, details)


def take_to_trash(table, row_id):
    row = get(f"SELECT * FROM {table} WHERE id=?", (row_id,))
    if not row:
        return
    execute(
        "INSERT INTO trash(table_name,row_id,deleted_at,data) VALUES(?,?,?,?)",
        (table, row_id, now(), json.dumps(row, ensure_ascii=False)),
    )


def restore_from_trash(trash_id):
    row = get("SELECT * FROM trash WHERE id=?", (trash_id,))
    if not row:
        return False
    data = json.loads(row["data"])
    table = row["table_name"]
    cols = ", ".join(data.keys())
    q = ", ".join(["?"] * len(data))
    execute(f"INSERT OR REPLACE INTO {table}({cols}) VALUES({q})", tuple(data.values()))
    execute("DELETE FROM trash WHERE id=?", (trash_id,))
    return True


def to_archive(table, row_id):
    row = get(f"SELECT * FROM {table} WHERE id=?", (row_id,))
    if not row:
        return
    execute(
        "INSERT INTO archive(table_name,row_id,archived_at,data) VALUES(?,?,?,?)",
        (table, row_id, now(), json.dumps(row, ensure_ascii=False)),
    )


def jload(s, default=None):
    if not s:
        return default if default is not None else []
    try:
        return json.loads(s)
    except Exception:
        return default if default is not None else []
