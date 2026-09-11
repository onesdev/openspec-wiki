"""考生侧：我的考试、试做判分。

`my_exams` 是「循环 append 组装数组」的典型写法：
函数体里确实有一条 `SELECT * FROM exams`，但返回值不是它，
而是 `out.append({...})` 拼出来的四个字段——SELECT 兜底不能盖掉它。
"""
from fastapi import APIRouter, Depends, HTTPException

from .. import db

router = APIRouter(prefix="/api/student")

StudentDep = "require_student"


@router.get("/my-exams")
def my_exams(me: dict = Depends(StudentDep)):
    rows = db.query("SELECT * FROM exams WHERE status = 'published'")
    out = []
    for r in rows:
        out.append({"id": r["id"], "name": r["name"],
                    "duration_min": r["duration_min"], "started": False})
    return out


@router.post("/trial/{qid}/submit")
def trial_submit(qid: int, payload: dict, me: dict = Depends(StudentDep)):
    lang = payload.get("lang") or "python"
    code = payload.get("code")
    if code is None:
        raise HTTPException(status_code=400, detail="代码不能为空")
    return {"passed": 1, "total": 1, "score": 100}
