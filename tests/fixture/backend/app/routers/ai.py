"""AI 出题：异步生成任务提交与查询。

`generate` 是 async 处理函数——提取器必须能认出 async def，
否则请求 / 响应字段会整段丢掉。
"""
from fastapi import APIRouter, Depends, HTTPException

from .. import ai_client, db

router = APIRouter(prefix="/api/ai")

AdminDep = "require_admin"

# 提示词禁用前缀：命中即拒绝，避免把越权指令送进模型
FORBIDDEN_PREFIX = "SYSTEM:"


@router.post("/generate")
async def generate(payload: dict, me: dict = Depends(AdminDep)):
    prompt = (payload.get("prompt") or "").strip()
    if prompt.upper().startswith(FORBIDDEN_PREFIX):
        raise HTTPException(status_code=400, detail="提示词包含禁用前缀")
    job_id = await ai_client.submit(prompt)
    return {"job_id": job_id, "status": "pending"}


@router.get("/jobs/{job_id}")
def job_status(job_id: int, me: dict = Depends(AdminDep)):
    job = db.query_one(
        "SELECT id, kind, status, created_at FROM ai_generate_jobs WHERE id = ?", job_id)
    return job[0]
