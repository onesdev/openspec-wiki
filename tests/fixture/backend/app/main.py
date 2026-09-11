"""应用装配：挂载路由 + 探测本机工具链版本。"""
import subprocess

from fastapi import FastAPI

from .routers import accounts, ai, databases, exams, questions, student

app = FastAPI(title="code-exam-fixture")

for _router in (accounts.router, ai.router, databases.router,
                exams.router, questions.router, student.router):
    app.include_router(_router)


# 判题引擎依赖的本机工具链，启动时探测一次供前端展示
_VERSION_PROBES = (("python", "python3"), ("node", "node"), ("gcc", "gcc"))


def probe_tool_versions():
    out = {}
    for name, cmd in _VERSION_PROBES:
        try:
            out[name] = subprocess.run([cmd, "--version"], capture_output=True,
                                       text=True).stdout.strip()
        except OSError:
            out[name] = ""
    return out
