#!/usr/bin/env python3
"""openspec-wiki 九类哈希的增量触发回归测试（纯 CLI，夹具置于 /tmp）。"""
import json
import os
import shutil
import subprocess
import sys
import time

STATE = os.path.expanduser("~/.workbuddy/skills/openspec-wiki/scripts/wiki_state.py")
DEFAULT_PROJECT = "/Users/jimmy/Desktop/workspace/机考系统/code-exam"
PROJECT = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PROJECT
BASE = "/tmp/wiki-regression/fixture"
results = []
t0 = time.time()


def run(project, *argv):
    out = subprocess.run([sys.executable, STATE, *argv, project],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def check(name, got, want):
    ok = got == want
    results.append(ok)
    print("%s  %s  [%.0fs]" % ("PASS" if ok else "FAIL", name, time.time() - t0), flush=True)
    if not ok:
        print("      got  = %r\n      want = %r" % (got, want), flush=True)


ign = shutil.ignore_patterns("node_modules", "__pycache__", "dist", ".git")
proj = os.path.join(BASE, "proj")
if os.path.isdir(proj):
    shutil.rmtree(proj)
os.makedirs(proj)
shutil.copytree(os.path.join(PROJECT, "openspec"), os.path.join(proj, "openspec"), ignore=ign)
shutil.copytree(os.path.join(PROJECT, "wiki"), os.path.join(proj, "wiki"), ignore=ign)
shutil.copytree(os.path.join(PROJECT, "backend"), os.path.join(proj, "backend"), ignore=ign)
shutil.copytree(os.path.join(PROJECT, "frontend"), os.path.join(proj, "frontend"), ignore=ign)
for f in ("README.md", "start.sh"):
    shutil.copy(os.path.join(PROJECT, f), os.path.join(proj, f))
os.remove(os.path.join(proj, "wiki", ".wiki-manifest.json"))
print("夹具就绪 [%.0fs]" % (time.time() - t0), flush=True)

p = run(proj, "plan")
check("1  full 模式", p["mode"], "full")
check("1  七个页面进入待生成清单", p["artifactsToGenerate"],
      ["README.md", "architecture.md", "decisions.md", "glossary.md",
       "api.md", "data-model.md", "integrations.md", "specs/*.md", "changelog.md"])
check("1  pendingChanges = 23", len(p["pendingChanges"]), 23)
check("1  pendingDecisions = 22", len(p["pendingDecisions"]), 22)
check("1  三类声明页均待生成",
      [p["apiDirty"], p["dataModelDirty"], p["integrationDirty"]], [True, True, True])
check("1  统计到核心端点与表",
      [p["stats"]["apiEndpoints"] > 50, p["stats"]["dataTables"] > 10], [True, True])

for fn in ("architecture.md", "decisions.md", "glossary.md", "api.md",
           "data-model.md", "integrations.md"):
    open(os.path.join(proj, "wiki", fn), "w").write("# stub\n")
run(proj, "commit", "--caps", ",".join(p["allCapabilities"]),
    "--change-ids", ",".join(c["id"] for c in p["pendingChanges"]),
    "--decisions", ",".join(c["id"] for c in p["pendingDecisions"]),
    "--overview", "--architecture", "--glossary", "--api", "--data-model", "--integrations")

p = run(proj, "plan")
check("2  全量记账后计划为空", p["artifactsToGenerate"], [])
check("2  各 dirty 标志归零",
      [p["overviewDirty"], p["architectureDirty"], p["glossaryDirty"],
       p["apiDirty"], p["dataModelDirty"], p["integrationDirty"]],
      [False, False, False, False, False, False])

PROBE = '\n\n@router.get("/probe")\ndef probe_endpoint():\n    pass\n'
exams = os.path.join(proj, "backend", "app", "routers", "exams.py")
orig = open(exams, encoding="utf-8").read()
open(exams, "w", encoding="utf-8").write(orig + PROBE)
p = run(proj, "plan")
check("3  新增路由 → apiDirty", p["apiDirty"], True)
check("3  不影响数据/集成/架构",
      [p["dataModelDirty"], p["integrationDirty"], p["architectureDirty"]], [False, False, False])
run(proj, "commit", "--api")

# 声明完全不变，只在文件开头插入空行 → 全部行号整体位移
open(exams, "w", encoding="utf-8").write("\n" + orig + PROBE)
p = run(proj, "plan")
check("4  仅行号整体位移 → apiDirty 不触发", p["apiDirty"], False)

open(os.path.join(proj, "backend", "selftest_api.py"), "a", encoding="utf-8").write(
    '\n\n@app.get("/probe-aux")\ndef probe_aux():\n    pass\n')
p = run(proj, "plan")
check("5  仅改自测文件 → apiDirty 不触发", p["apiDirty"], False)

open(os.path.join(proj, "backend", "app", "db.py"), "a", encoding="utf-8").write(
    "\n\ndef _migrate_v9(conn):\n    conn.execute(\n"
    "        \"CREATE TABLE IF NOT EXISTS audit_trail(\"\n"
    "        \" id INTEGER PRIMARY KEY, note TEXT)\")\n")
p = run(proj, "plan")
check("6  新增建表语句 → dataModelDirty", p["dataModelDirty"], True)
check("6  不影响接口/集成", [p["apiDirty"], p["integrationDirty"]], [False, False])
run(proj, "commit", "--data-model")

open(os.path.join(proj, "backend", "app", "main.py"), "a", encoding="utf-8").write(
    '\n\nimport redis\n\nredis_client = redis.Redis(host="127.0.0.1", port=6379)\n')
p = run(proj, "plan")
check("7  引入消息队列 → integrationDirty", p["integrationDirty"], True)
check("7  不影响接口/数据", [p["apiDirty"], p["dataModelDirty"]], [False, False])
check("7  extract 识别 MQ 使用",
      run(proj, "extract", "--only", "integrations")["integrations"]["usesMessageQueue"], True)
run(proj, "commit", "--integrations")

# --- 请求 / 响应字段结构的增量口径 -----------------------------------------
p = run(proj, "plan")
check("8  全部记账后计划为空", p["artifactsToGenerate"], [])

# 8) 在 handler 体内插入与本接口字段声明无关的语句 → apiDirty 不应触发
src = open(exams, encoding="utf-8").read()
open(exams, "w", encoding="utf-8").write(
    src.replace("def list_exams(me: dict = Depends(GraderDep)):\n",
                "def list_exams(me: dict = Depends(GraderDep)):\n"
                "    _audit_log(\"list\")\n"))
p = run(proj, "plan")
check("8  函数体内加无关语句 → apiDirty 不触发", p["apiDirty"], False)

# 9) 改响应组装辅助函数的返回结构 → apiDirty 应触发（一层内联）
src = open(exams, encoding="utf-8").read()
open(exams, "w", encoding="utf-8").write(
    src.replace('        "created_at": row["created_at"],\n',
                '        "created_at": row["created_at"],\n'
                '        "archived": False,\n'))
p = run(proj, "plan")
check("9  辅助函数返回新增字段 → apiDirty", p["apiDirty"], True)
check("9  不影响数据模型", p["dataModelDirty"], False)
run(proj, "commit", "--api")

# 10) 给 DDL 表加列 → 数据模型触发，且被 `SELECT *` 兜底端点的字段随之变化 → 接口页也触发
stu = os.path.join(proj, "backend", "app", "routers", "student.py")
open(stu, "a", encoding="utf-8").write(
    '\n\n@router.get("/probe-rows")\n'
    'def probe_rows():\n'
    '    """SELECT * 兜底探针。"""\n'
    '    rows = db.query("SELECT * FROM exams")\n'
    '    return rows\n')
run(proj, "commit", "--api")
check("10 探针端点记账后无脏标记", run(proj, "plan")["apiDirty"], False)

db = os.path.join(proj, "backend", "app", "db.py")
src = open(db, encoding="utf-8").read()
open(db, "w", encoding="utf-8").write(
    src.replace("        status TEXT NOT NULL CHECK(status IN ('draft','published','closed')),",
                "        status TEXT NOT NULL CHECK(status IN ('draft','published','closed')),\n"
                "        remark TEXT,"))
p = run(proj, "plan")
check("10 建表语句加列 → dataModelDirty", p["dataModelDirty"], True)
check("10 列变化联动接口页（SELECT * 兜底端点）", p["apiDirty"], True)
run(proj, "commit", "--api", "--data-model")

# 11) 字段结构抽取内容断言
ex = run(proj, "extract", "--only", "api")["api"]
eps = [e for g in ex["groups"] for e in g["endpoints"]]
by = {e["handler"]: e for e in eps}

ce = by.get("create_exam", {})
check("11 create_exam 识别请求体参数", ce.get("bodyParam"), "payload")
check("11 create_exam 请求字段名与类型",
      [(f["name"], f["type"], f["required"]) for f in ce.get("request", [])],
      [("name", "string", True), ("duration_min", "integer", True),
       ("student_count", "integer", True), ("question_ids", "array", False)])
check("11 create_exam 响应字段来自辅助函数内联",
      (ce.get("response") or {}).get("source", "").startswith("_exam_public()"),
      True)
check("11 create_exam 错误约定被提取",
      len(ce.get("errors") or []) >= 3, True)

le = by.get("list_exams", {})
check("11 数组型响应 kind=array", (le.get("response") or {}).get("kind"), "array")
check("11 响应字段类型取自 DDL 列",
      (le["response"]["fields"][0]["name"], le["response"]["fields"][0]["type"]),
      ("id", "INTEGER"))

cj = by.get("cancel_job", {})
check("11 Depends 注入形参不得被当作请求体", cj.get("bodyParam"), "")

gn = by.get("generate", {})
check("11 async handler 的响应结构被提取",
      (gn.get("response") or {}).get("kind"), "object")
check("11 async handler 的请求字段被提取",
      [f["name"] for f in gn.get("request", [])], ["prompt"])

# 12) DDL 列抽取保真：名为 key 的列 / 拼接式建表 / 同名示例小表不得覆盖核心表
open(db, "a", encoding="utf-8").write(
    "\n\ndef _migrate_v10(conn):\n    conn.execute(\n"
    '        "CREATE TABLE IF NOT EXISTS audit_trail("'
    ' " id INTEGER PRIMARY KEY, key TEXT PRIMARY KEY, note TEXT,"'
    ' " UNIQUE(id, note))")\n'
    "\n\ndef _example_db(conn):\n"
    '    conn.execute("CREATE TABLE users(id INTEGER PRIMARY KEY, name TEXT)")\n')
dm = run(proj, "extract", "--only", "dataModel")["dataModel"]
tbl = {t["name"]: t for t in dm["tables"]}
check("12 拼接式建表语句的列被解析",
      [c["name"] for c in tbl["audit_trail"]["columns"]],
      ["id", "key", "note"])
check("12 名为 key 的列未被当作索引定义丢弃",
      [c["constraints"] for c in tbl["audit_trail"]["columns"] if c["name"] == "key"],
      [["PK"]])
check("12 表级 UNIQUE 未被当作列",
      "UNIQUE" in [c["name"] for c in tbl["audit_trail"]["columns"]], False)
check("12 同名示例小表不覆盖核心表列", len(tbl["users"]["columns"]), 9)
check("12 occurrences 记录各声明列数",
      sorted(o["cols"] for o in tbl["users"]["occurrences"]), [2, 2, 3, 9])

# 13) 必填判定口径：多变量 not 守卫 / 枚举 not in 守卫 / is None 守卫；
#     手握默认值的字段不得因 `if x == "枚举值":` 这类分支被误判必填
check("13 多变量 not 守卫 → 相关字段均必填",
      [(f["name"], f["required"]) for f in by["create_account"]["request"]],
      [("username", True), ("password", True), ("role", True),
       ("display_name", False)])
check("13 有默认值的字段不因枚举分支误判必填",
      [(f["name"], f["required"]) for f in gn["request"]], [("prompt", False)])
check("13 is None 守卫 → 必填",
      [(f["name"], f["required"]) for f in by["trial_submit"]["request"]],
      [("lang", False), ("code", True)])

# 14) 响应结构回溯口径
ex2 = run(proj, "extract", "--only", "api")["api"]
by2 = {e["handler"]: e for g in ex2["groups"] for e in g["endpoints"]}
check("14 list.append 组装的返回值按实际字段提取",
      [f["name"] for f in by2["my_exams"]["response"]["fields"]],
      ["id", "name", "duration_min", "started"])
check("14 SELECT * 兜底端点字段随 DDL 加列变化",
      "remark" in [f["name"] for f in by2["probe_rows"]["response"]["fields"]], True)
check("14 变量经辅助函数组装 + 补字段的响应被还原",
      [f["name"] for f in by2["get_database"]["response"]["fields"]][:3],
      ["id", "uid", "name"])
check("14 本地变量字典字面量 + 补字段的响应被还原",
      [f["name"] for f in
       [e for g in ex2["groups"] if g["prefix"] == "/api/questions"
        for e in g["endpoints"] if e["handler"] == "question_detail"][0]
       ["response"]["fields"]],
      ["id", "title", "type", "files", "referenced", "database_uid", "database_name"])
check("14 内置资产端点识别为二进制下载",
      by2["template_pack"]["response"]["kind"], "raw")
check("14 无未提取的响应结构",
      [e["handler"] for g in ex2["groups"] for e in g["endpoints"]
       if (e.get("response") or {}).get("kind") == "unknown"], [])

# 15) 动态 ALTER 补列清单（(表, 列, 列定义) 三元组）应并入有效列集
dmx = run(proj, "extract", "--only", "dataModel")["dataModel"]
tx = {t["name"]: t for t in dmx["tables"]}
check("15 补列清单的列并入目标表",
      [(c["name"], c["type"]) for c in tx["questions"]["columns"] if c.get("addedAt")],
      [("database_uid", "TEXT")])
check("15 补列记录来源位置",
      [c["addedAt"].rsplit(":", 1)[0] for c in tx["submissions"]["columns"]
       if c.get("addedAt")],
      ["backend/app/db.py"])
check("15 补列清单里的既有列不重复计入",
      len([c["name"] for c in tx["ai_generate_jobs"]["columns"]]) ==
      len({c["name"] for c in tx["ai_generate_jobs"]["columns"]}), True)
check("15 补列写入 alterations",
      sorted({a["column"] for a in dmx["alterations"] if a["action"] == "ADD COLUMN"}),
      ["database_uid", "kind", "lang"])

print("\n%d/%d 通过，总耗时 %.0fs" % (sum(results), len(results), time.time() - t0))
sys.exit(0 if all(results) else 1)
