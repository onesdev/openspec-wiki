"""接口自测（辅助文件——不参与核心提取与哈希）。

名字含 `selftest` 的文件一律归为辅助：这里的建表语句是自测种子库、
路由是自测桩，混进正文会污染事实。
"""
import sqlite3

# 自测种子库：字段最少的一份同名表
SEED_DDL = "CREATE TABLE users(id INTEGER PRIMARY KEY, name TEXT)"

# 只存在于自测里的表——不得出现在主表清单中
SELFTEST_DDL = "CREATE TABLE selftest_runs(id INTEGER PRIMARY KEY, note TEXT)"


def seed(conn):
    conn.execute(SEED_DDL)
    conn.execute(SELFTEST_DDL)
    conn.execute("INSERT INTO users(name) VALUES ('u1')")


@app.get("/probe-existing")
def probe_existing():
    return {"ok": True}
