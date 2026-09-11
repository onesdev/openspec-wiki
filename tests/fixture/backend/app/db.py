"""SQLite 建表、索引与增量迁移。

裸 sqlite3，无 ORM —— 表结构就是下面这份 DDL，字段类型以它为准。
"""

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'student',
    display_name TEXT,
    created_at TEXT,
    updated_at TEXT,
    last_login TEXT,
    disabled INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS exams(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    duration_min INTEGER NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('draft','published','closed')),
    created_at TEXT,
    created_by INTEGER,
    FOREIGN KEY(created_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS questions(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    type TEXT NOT NULL,
    files TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS submissions(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exam_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    question_id INTEGER NOT NULL,
    correct INTEGER NOT NULL DEFAULT 0,
    score INTEGER NOT NULL DEFAULT 0,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS ai_generate_jobs(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS databases(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid TEXT NOT NULL,
    name TEXT NOT NULL,
    script TEXT,
    created_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_submissions_lookup
    ON submissions(exam_id, user_id, question_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_exams_name ON exams(name);
"""

# 动态补列清单：(表, 列, 列定义)。
# SCHEMA 只对全新建库生效，存量库靠这份清单补齐后来新增的列。
# 清单里的列若已存在于 SCHEMA（如 ai_generate_jobs.kind），迁移时会自动跳过。
ALTER_COLUMNS = [
    ("questions", "database_uid", "TEXT"),
    ("submissions", "lang", "TEXT NOT NULL"),
    ("ai_generate_jobs", "kind", "TEXT"),
]

# saved_codes 的唯一键要从 (exam,user,question) 扩到含 lang，
# SQLite 不支持改唯一键，只能建新表 → 拷数 → 改名。
_SAVED_CODES_V2 = (
    "CREATE TABLE IF NOT EXISTS saved_codes_v2("
    " id INTEGER PRIMARY KEY AUTOINCREMENT,"
    " exam_id INTEGER NOT NULL,"
    " user_id INTEGER NOT NULL,"
    " question_id INTEGER NOT NULL,"
    " lang TEXT NOT NULL,"
    " code TEXT,"
    " UNIQUE(exam_id, user_id, question_id, lang))"
)


def migrate(conn):
    """把存量库补齐到当前 schema。"""
    for table, column, coldef in ALTER_COLUMNS:
        existing = {r[1] for r in conn.execute("PRAGMA table_info(%s)" % table)}
        if column not in existing:
            conn.execute("ALTER TABLE %s ADD COLUMN %s %s" % (table, column, coldef))
    conn.execute(_SAVED_CODES_V2)
    conn.execute("DROP TABLE IF EXISTS saved_codes")
    conn.execute("ALTER TABLE saved_codes_v2 RENAME TO saved_codes")
