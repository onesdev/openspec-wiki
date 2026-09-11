"""SQL 题库：列表与详情。

`get_database` 是「辅助函数组装 + 事后补统计字段」的写法：
主体结构来自 `_row_brief()`，`table_count` / `sample_rows` 在返回前才补上。
"""
from fastapi import APIRouter, Depends

from .. import db

router = APIRouter(prefix="/api/databases")

AdminDep = "require_admin"


def _row_brief(row):
    """题库摘要：列表与详情共用同一份结构。"""
    return {
        "id": row["id"],
        "uid": row["uid"],
        "name": row["name"],
        "script": row["script"],
        "created_at": row["created_at"],
    }


@router.get("")
def list_databases(me: dict = Depends(AdminDep)):
    rows = db.query("SELECT id, uid, name, script, created_at FROM databases")
    return rows


@router.get("/{db_id}")
def get_database(db_id: int, me: dict = Depends(AdminDep)):
    row = db.query_one(
        "SELECT id, uid, name, script, created_at FROM databases WHERE id = ?", db_id)
    brief = _row_brief(row)
    brief["table_count"] = db.count_tables(db_id)
    brief["sample_rows"] = 0
    return brief
