#!/usr/bin/env python3
"""openspec-wiki 回归测试：增量触发口径 + 字段结构提取准确性。

夹具是技能自带的 `tests/fixture/`（小号 FastAPI + 裸 SQLite 工程），
整份复制到临时目录再改，**不动夹具本体**，也不依赖任何外部项目。

改过 `scripts/wiki_state.py` 就跑一遍：

    python3 tests/incremental_regression.py

全绿则退出码 0，任一断言不过则非 0。断言分两类：

* 甲组（1~10）触发口径——该重生成的必须触发，不该触发的必须不触发。
  漏触发会让 wiki 静默过期，比误触发危险得多，所以两个方向都要钉。
* 乙组（11~15）提取准确性——抽出来的字段名 / 类型 / 必填 / 列约束对不对。
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, os.pardir, "scripts", "wiki_state.py")
FIXTURE = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "fixture")
PROJ = os.path.join(tempfile.gettempdir(), "wiki-regression", "proj")

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


def edit(rel, fn):
    """读 → 改 → 写回夹具副本里的一份文件。"""
    path = os.path.join(PROJ, rel)
    with open(path, encoding="utf-8") as f:
        src = f.read()
    with open(path, "w", encoding="utf-8") as f:
        f.write(fn(src))


def append(rel, text):
    with open(os.path.join(PROJ, rel), "a", encoding="utf-8") as f:
        f.write(text)


# ---------------------------------------------------------------- 夹具构建

if not os.path.isfile(os.path.join(FIXTURE, "openspec", "changes", "add-audit-trail",
                                   "proposal.md")):
    sys.exit("夹具不完整或路径不对：%s\n"
             "（期望目录下有 openspec/changes/add-audit-trail/proposal.md；"
             "也可用第一个参数指定夹具路径）" % FIXTURE)

if os.path.isdir(PROJ):
    shutil.rmtree(PROJ)
shutil.copytree(FIXTURE, PROJ, ignore=shutil.ignore_patterns("__pycache__", ".git"))
print("夹具就绪：%s [%.0fs]" % (PROJ, time.time() - t0), flush=True)

# ---------------------------------------------------------------- 1) 全量起点

p = run(PROJ, "plan")
check("1  full 模式", p["mode"], "full")
check("1  九类页面进入待生成清单", p["artifactsToGenerate"],
      ["README.md", "architecture.md", "decisions.md", "glossary.md",
       "api.md", "data-model.md", "integrations.md", "specs/*.md", "changelog.md"])
check("1  归档变更数", len(p["pendingChanges"]), 3)
check("1  决策数", len(p["pendingDecisions"]), 3)
check("1  能力清单", p["allCapabilities"],
      ["exam-core", "grading-pipeline", "question-catalog"])
check("1  进行中变更被单独列出", [c["id"] for c in p["activeChanges"]], ["add-audit-trail"])
check("1  三类声明页均待生成",
      [p["apiDirty"], p["dataModelDirty"], p["integrationDirty"]], [True, True, True])
check("1  统计到端点与表",
      [p["stats"]["apiEndpoints"], p["stats"]["dataTables"]], [16, 7])

os.makedirs(os.path.join(PROJ, "wiki"), exist_ok=True)
for fn in ("README.md", "architecture.md", "decisions.md", "glossary.md",
           "api.md", "data-model.md", "integrations.md"):
    open(os.path.join(PROJ, "wiki", fn), "w").write("# stub\n")
# 能力页也要先占位，否则 specs/*.md 永远挂在待生成清单上
os.makedirs(os.path.join(PROJ, "wiki", "specs"), exist_ok=True)
for cap in p["allCapabilities"]:
    open(os.path.join(PROJ, "wiki", "specs", cap + ".md"), "w").write("# stub\n")
run(PROJ, "commit", "--caps", ",".join(p["allCapabilities"]),
    "--change-ids", ",".join(c["id"] for c in p["pendingChanges"]),
    "--decisions", ",".join(c["id"] for c in p["pendingDecisions"]),
    "--overview", "--architecture", "--glossary", "--api", "--data-model", "--integrations")

# ---------------------------------------------------------------- 2) 记账后清空

p = run(PROJ, "plan")
check("2  全量记账后计划为空", p["artifactsToGenerate"], [])
check("2  各 dirty 标志归零",
      [p["overviewDirty"], p["architectureDirty"], p["glossaryDirty"],
       p["apiDirty"], p["dataModelDirty"], p["integrationDirty"]],
      [False, False, False, False, False, False])

# ---------------------------------------------------------------- 3~7) 触发与不触发

PROBE = '\n\n@router.get("/probe")\ndef probe_endpoint():\n    pass\n'
append("backend/app/routers/exams.py", PROBE)
p = run(PROJ, "plan")
check("3  新增路由 → apiDirty", p["apiDirty"], True)
check("3  不影响数据 / 集成 / 架构",
      [p["dataModelDirty"], p["integrationDirty"], p["architectureDirty"]], [False, False, False])
run(PROJ, "commit", "--api")

# 声明完全不变，只在文件开头插入空行 → 全部行号整体位移
edit("backend/app/routers/exams.py", lambda s: "\n" + s)
check("4  仅行号整体位移 → apiDirty 不触发", run(PROJ, "plan")["apiDirty"], False)

append("backend/selftest_api.py",
       '\n\n@app.get("/probe-aux")\ndef probe_aux():\n    pass\n')
check("5  仅改辅助文件 → apiDirty 不触发", run(PROJ, "plan")["apiDirty"], False)

append("backend/app/db.py",
       "\n\ndef _migrate_v8(conn):\n    conn.execute(\n"
       "        \"CREATE TABLE IF NOT EXISTS audit_trail(\""
       " \" id INTEGER PRIMARY KEY, note TEXT)\")\n")
p = run(PROJ, "plan")
check("6  新增建表语句 → dataModelDirty", p["dataModelDirty"], True)
check("6  不影响接口 / 集成", [p["apiDirty"], p["integrationDirty"]], [False, False])
run(PROJ, "commit", "--data-model")

append("backend/app/main.py",
       '\n\nimport redis\n\nredis_client = redis.Redis(host="127.0.0.1", port=6379)\n')
p = run(PROJ, "plan")
check("7  引入消息队列 → integrationDirty", p["integrationDirty"], True)
check("7  不影响接口 / 数据", [p["apiDirty"], p["dataModelDirty"]], [False, False])
check("7  extract 识别 MQ 使用",
      run(PROJ, "extract", "--only", "integrations")["integrations"]["usesMessageQueue"], True)
run(PROJ, "commit", "--integrations")

# ---------------------------------------------------------------- 8~10) 函数体改动的粒度

check("8  全部记账后计划为空", run(PROJ, "plan")["artifactsToGenerate"], [])

edit("backend/app/routers/exams.py",
     lambda s: s.replace("def list_exams(me: dict = Depends(GraderDep)):\n",
                         "def list_exams(me: dict = Depends(GraderDep)):\n"
                         '    _audit_log("list")\n'))
check("8  函数体内加无关语句 → apiDirty 不触发", run(PROJ, "plan")["apiDirty"], False)

# 改响应组装辅助函数的返回结构 → 一层内联，应触发
edit("backend/app/routers/exams.py",
     lambda s: s.replace('        "created_at": row["created_at"],\n',
                         '        "created_at": row["created_at"],\n'
                         '        "archived": False,\n'))
p = run(PROJ, "plan")
check("9  辅助函数返回新增字段 → apiDirty", p["apiDirty"], True)
check("9  不影响数据模型", p["dataModelDirty"], False)
run(PROJ, "commit", "--api")

# SELECT * 兜底端点：DDL 加列后它的响应字段随之变化，接口页必须联动触发
append("backend/app/routers/student.py",
       '\n\n@router.get("/probe-rows")\n'
       'def probe_rows():\n'
       '    """SELECT * 兜底探针。"""\n'
       '    rows = db.query("SELECT * FROM exams")\n'
       '    return rows\n')
run(PROJ, "commit", "--api")
check("10 探针端点记账后无脏标记", run(PROJ, "plan")["apiDirty"], False)

edit("backend/app/db.py",
     lambda s: s.replace(
         "    status TEXT NOT NULL CHECK(status IN ('draft','published','closed')),",
         "    status TEXT NOT NULL CHECK(status IN ('draft','published','closed')),\n"
         "    remark TEXT,"))
p = run(PROJ, "plan")
check("10 建表语句加列 → dataModelDirty", p["dataModelDirty"], True)
check("10 列变化联动接口页（SELECT * 兜底端点）", p["apiDirty"], True)
run(PROJ, "commit", "--api", "--data-model")

# ---------------------------------------------------------------- 11) 请求 / 响应字段结构

ex = run(PROJ, "extract", "--only", "api")["api"]
ep = {e["handler"]: e for g in ex["groups"] for e in g["endpoints"]}

ce = ep.get("create_exam", {})
check("11 create_exam 识别请求体参数", ce.get("bodyParam"), "payload")
check("11 create_exam 请求字段名 / 类型 / 必填",
      [(f["name"], f["type"], f["required"]) for f in ce.get("request", [])],
      [("name", "string", True), ("duration_min", "integer", True),
       ("student_count", "integer", True), ("question_ids", "array", False)])
check("11 create_exam 响应来自辅助函数内联",
      (ce.get("response") or {}).get("source", "").startswith("_exam_public()"), True)
check("11 create_exam 错误约定被提取", len(ce.get("errors") or []), 3)

le = ep.get("list_exams", {})
check("11 数组型响应 kind=array", (le.get("response") or {}).get("kind"), "array")
check("11 响应字段类型取自 DDL 列",
      (le["response"]["fields"][0]["name"], le["response"]["fields"][0]["type"]),
      ("id", "INTEGER"))

check("11 Depends 注入形参不得被当作请求体",
      [ep["cancel_job"].get("bodyParam"), ep["job_status"].get("bodyParam")], ["", ""])

gn = ep.get("generate", {})
check("11 async handler 的响应结构被提取",
      (gn.get("response") or {}).get("kind"), "object")
check("11 async handler 的请求字段被提取",
      [f["name"] for f in gn.get("request", [])], ["prompt"])

# ---------------------------------------------------------------- 12) DDL 列抽取保真

append("backend/app/db.py",
       "\n\ndef _migrate_v9(conn):\n    conn.execute(\n"
       "        \"CREATE TABLE IF NOT EXISTS audit_trail(\""
       " \" id INTEGER PRIMARY KEY, key TEXT PRIMARY KEY, note TEXT,\""
       " \" UNIQUE(id, note))\")\n"
       "\n\ndef _example_db(conn):\n"
       '    conn.execute("CREATE TABLE users(id INTEGER PRIMARY KEY, name TEXT)")\n')
dm = run(PROJ, "extract", "--only", "dataModel")["dataModel"]
tbl = {t["name"]: t for t in dm["tables"]}
check("12 相邻字符串拼接的建表语句列被解析",
      [c["name"] for c in tbl["audit_trail"]["columns"]], ["id", "key", "note"])
check("12 名为 key 的列未被当作索引定义丢弃",
      [c["constraints"] for c in tbl["audit_trail"]["columns"] if c["name"] == "key"],
      [["PK"]])
check("12 表级 UNIQUE 未被当作列",
      "UNIQUE" in [c["name"] for c in tbl["audit_trail"]["columns"]], False)
check("12 同名示例小表不覆盖核心表列", len(tbl["users"]["columns"]), 9)
check("12 occurrences 记录各声明列数",
      sorted(o["cols"] for o in tbl["users"]["occurrences"]), [2, 2, 3, 9])
check("12 只出现在辅助文件的表不进主表清单",
      ([t["name"] for t in dm["auxiliaryTables"]], len(dm["tables"])), (["selftest_runs"], 8))

# ---------------------------------------------------------------- 13) 必填判定口径

check("13 多变量 not 守卫 → 相关字段均必填",
      [(f["name"], f["required"]) for f in ep["create_account"]["request"]],
      [("username", True), ("password", True), ("role", True), ("display_name", False)])
check("13 有默认值的字段不因内容分支误判必填",
      [(f["name"], f["required"]) for f in gn["request"]], [("prompt", False)])
check("13 is None 守卫 → 必填",
      [(f["name"], f["required"]) for f in ep["trial_submit"]["request"]],
      [("lang", False), ("code", True)])
check("13 not in 枚举守卫 → 必填",
      [(f["name"], f["required"]) for f in ep["set_exam_status"]["request"]],
      [("status", True)])
check("13 内容分支 raise（x == \"sms\"）不得判成必填",
      [(f["name"], f["required"]) for f in ep["publish_exam"]["request"]],
      [("notify", False)])

# ---------------------------------------------------------------- 14) 响应结构回溯

by2 = {e["handler"]: e for g in run(PROJ, "extract", "--only", "api")["api"]["groups"]
       for e in g["endpoints"]}
check("14 list.append 组装的返回值按实际字段提取",
      [f["name"] for f in by2["my_exams"]["response"]["fields"]],
      ["id", "name", "duration_min", "started"])
check("14 SELECT * 兜底端点字段随 DDL 加列变化",
      "remark" in [f["name"] for f in by2["probe_rows"]["response"]["fields"]], True)
check("14 变量经辅助函数组装 + 补字段的响应被还原",
      [f["name"] for f in by2["get_database"]["response"]["fields"]][:3], ["id", "uid", "name"])
check("14 补字段右值带行尾注释时类型仍回落 DDL 列",
      [f["type"] for f in by2["get_database"]["response"]["fields"] if f["name"] == "script"],
      ["TEXT"])
check("14 补字段的来源表达式已剥除行尾注释",
      [f["from"] for f in by2["get_database"]["response"]["fields"] if f["name"] == "script"],
      ['row["script"]'])
check("14 局部变量字典字面量（含行内注释）+ 补字段的响应被还原",
      [f["name"] for f in by2["question_detail"]["response"]["fields"]],
      ["id", "title", "type", "files", "referenced", "database_uid", "database_name"])
check("14 内置资产端点识别为二进制下载",
      (by2["template_pack"]["response"] or {}).get("kind"), "raw")
check("14 无未提取的响应结构",
      [e["handler"] for g in ex["groups"] for e in g["endpoints"]
       if (e.get("response") or {}).get("kind") == "unknown"], [])

# ---------------------------------------------------------------- 15) 动态补列

tx = {t["name"]: t for t in run(PROJ, "extract", "--only", "dataModel")["dataModel"]["tables"]}
check("15 补列清单的列并入目标表",
      [(c["name"], c["type"]) for c in tx["questions"]["columns"] if c.get("addedAt")],
      [("database_uid", "TEXT")])
check("15 补列记录来源位置",
      [c["addedAt"].rsplit(":", 1)[0] for c in tx["submissions"]["columns"] if c.get("addedAt")],
      ["backend/app/db.py"])
check("15 补列清单里的既有列不重复计入",
      len([c["name"] for c in tx["ai_generate_jobs"]["columns"]]),
      len({c["name"] for c in tx["ai_generate_jobs"]["columns"]}))
check("15 补列写入 alterations",
      sorted({a["column"] for a in
              run(PROJ, "extract", "--only", "dataModel")["dataModel"]["alterations"]
              if a["action"] == "ADD COLUMN"}),
      ["database_uid", "kind", "lang"])

print("\n%d/%d 通过，总耗时 %.0fs" % (sum(results), len(results), time.time() - t0))
sys.exit(0 if all(results) else 1)
