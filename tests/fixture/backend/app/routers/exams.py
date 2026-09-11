"""考试管理：创建、列表、状态流转。

请求体是裸 dict（本项目不引入 Pydantic），字段靠 `payload.get()` 取值。
"""
from fastapi import APIRouter, Depends, HTTPException

from .. import db

router = APIRouter(prefix="/api/exams")

AdminDep = "require_admin"
GraderDep = "require_grader"

VALID_STATUS = ("draft", "published", "closed")


def _exam_public(row):
    """考试的对外结构：内部字段不外泄。"""
    return {
        "id": row["id"],
        "name": row["name"],
        "duration_min": row["duration_min"],
        "status": row["status"],
        "created_at": row["created_at"],
    }


@router.get("")
def list_exams(me: dict = Depends(GraderDep)):
    rows = db.query(
        "SELECT id, name, duration_min, status, created_at FROM exams ORDER BY id DESC")
    return rows


@router.post("")
def create_exam(payload: dict, me: dict = Depends(AdminDep)):
    name = (payload.get("name") or "").strip()
    duration_min = int(payload.get("duration_min") or 0)
    student_count = int(payload.get("student_count") or 0)
    question_ids = payload.get("question_ids") or []
    if not name:
        raise HTTPException(status_code=400, detail="考试名称不能为空")
    if duration_min <= 0:
        raise HTTPException(status_code=400, detail="考试时长必须为正整数")
    if student_count < 0:
        raise HTTPException(status_code=400, detail="考生人数不能为负数")
    row = db.create_exam(name, duration_min, student_count, question_ids)
    return _exam_public(row)


@router.post("/{exam_id}/status")
def set_exam_status(exam_id: int, payload: dict, me: dict = Depends(AdminDep)):
    status = payload.get("status")
    if status not in VALID_STATUS:
        raise HTTPException(status_code=400, detail="考试状态非法")
    return {"id": exam_id, "status": status}


@router.post("/{exam_id}/publish")
def publish_exam(exam_id: int, payload: dict, me: dict = Depends(AdminDep)):
    """发布考试；`notify` 有默认值，`== "sms"` 只是内容分支，不代表必填。"""
    notify = payload.get("notify") or "none"
    if notify == "sms":
        raise HTTPException(status_code=400, detail="暂不支持短信通知")
    return {"id": exam_id, "notified": notify}
