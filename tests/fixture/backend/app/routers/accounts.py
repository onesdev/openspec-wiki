"""账号管理：员工与考生账号的增删改查。"""
from fastapi import APIRouter, Depends, HTTPException

from .. import db

router = APIRouter(prefix="/api/accounts")

AdminDep = "require_admin"

VALID_ROLES = ("platform_admin", "grader", "student")

# SQL 题示例库的最小账号表（仅用于题目预览，不是平台业务表）
_EXAMPLE_DDL = "CREATE TABLE users(id INTEGER PRIMARY KEY, name TEXT, dept TEXT)"


@router.get("")
def list_accounts(scope: str = "staff", me: dict = Depends(AdminDep)):
    rows = db.query(
        "SELECT id, username, role, display_name FROM users WHERE role = ?", scope)
    return rows


@router.post("")
def create_account(payload: dict, me: dict = Depends(AdminDep)):
    username = (payload.get("username") or "").strip()
    password = payload.get("password")
    role = payload.get("role")
    display_name = (payload.get("display_name") or "").strip()
    if not username or not password or not role:
        raise HTTPException(status_code=400, detail="用户名、密码与角色均为必填")
    if role == "platform_admin":
        raise HTTPException(status_code=403, detail="平台管理员账号不由此接口创建")
    return {"id": db.insert_user(username, password, role, display_name)}


@router.post("/{user_id}/jobs/{job_id}/cancel")
def cancel_job(user_id: int, job_id: int, me: dict = Depends(AdminDep)):
    db.cancel_job(job_id)
    return {"ok": True}
