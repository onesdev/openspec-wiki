"""题库管理：列表、详情、内置资产下载。

`question_detail` 是「局部变量组装 + 事后补字段」的典型写法：
主结构在 `resp = {...}` 里，`database_name` 需要另查一次才能补上。
"""
from fastapi import APIRouter, Depends, Response

from .. import db

router = APIRouter(prefix="/api/questions")

AdminDep = "require_admin"
GraderDep = "require_grader"


def _db_name(uid):
    """按题库 uid 取展示名；查不到返回空串。"""
    row = db.query_one("SELECT name FROM databases WHERE uid = ?", uid)
    return row["name"] if row else ""


@router.get("")
def list_questions(me: dict = Depends(GraderDep)):
    rows = db.query("SELECT id, title, type, created_at FROM questions ORDER BY id DESC")
    return rows


@router.get("/template-pack")
def template_pack(me: dict = Depends(AdminDep)):
    data = db.build_template_zip()
    return Response(content=data, media_type="application/zip")


@router.get("/{qid}")
def question_detail(qid: int, me: dict = Depends(AdminDep)):
    row = db.query_one("SELECT id, title, type, files FROM questions WHERE id = ?", qid)
    resp = {
        "id": row["id"],      # 主键，前端用作路由参数
        "title": row["title"],
        "type": row["type"],
        "files": row["files"],
        "referenced": False,
    }
    resp["database_uid"] = row["database_uid"]
    resp["database_name"] = _db_name(row["database_uid"])
    return resp
