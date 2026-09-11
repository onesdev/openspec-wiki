"""OpenAI 兼容大模型调用——本项目唯一的外部 HTTP 依赖。

地址与模型名走环境变量，默认指向本机 Ollama。
"""
import os

import httpx

LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "http://127.0.0.1:11434/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "qwen2.5-14b-instruct")

_client = httpx.AsyncClient(base_url=LLM_BASE_URL, timeout=120)


async def submit(prompt):
    """提交一次对话补全，返回模型输出文本。"""
    resp = await _client.post("/chat/completions", json={
        "model": LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
    })
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]
