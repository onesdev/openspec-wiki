# 声明类提取：模式目录与口径

`api.md` / `data-model.md` / `integrations.md` 三页的事实源来自 `extract` 子命令。
本文件说明它**读什么、不读什么、覆盖哪些技术栈、如何降级**。

```bash
python3 <skill_dir>/scripts/wiki_state.py extract <项目路径> [--only api,dataModel,integrations]
```

## 读取边界（硬约束）

| 读 | 不读 |
|----|------|
| 路由装饰器、函数签名、权限依赖声明 | 函数体的业务实现逻辑（分支、循环、算法、副作用） |
| 函数体内的**字段声明**：请求体取值 `payload.get("x")`、返回结构（dict 字面量 / 辅助函数返回 / `SELECT` 列） | 调用链追踪、跨模块数据流 |
| DDL 语句（含**列名 / 类型 / 约束**）、ORM 模型声明、迁移语句 | 运行时数据、数据库文件内容 |
| HTTP 客户端调用点、URL / 配置键字面量 | 动态拼接的地址 |
| 依赖清单文件内容 | 第三方库源码 |
| design.md 的约束 / Non-Goals 节 | proposal.md 的实现任务细节 |

提取是**启发式模式匹配**，不是编译器级解析。宁可漏报并降级为"待补"，也不要臆测。

## 覆盖的技术栈模式

| 类别 | 已覆盖 | 识别方式 |
|------|--------|----------|
| HTTP 路由 | FastAPI / Flask | `APIRouter(prefix=...)` / `Blueprint(...)` + `@router.get/post/...` |
| | Express / Koa | `router.get('/path', ...)` / `app.use('/prefix', ...)` |
| | Spring（Java/Kotlin） | `@GetMapping/@PostMapping/...` + `@RequestMapping` 类前缀 |
| 权限 | FastAPI 依赖注入 | `Depends(Alias)` 并回溯 `Alias = require_roles("a","b")` |
| | Spring 注解 | `@PreAuthorize` / `@RolesAllowed`（记入 `authHint`） |
| 请求字段 | 裸 dict 请求体 | 形参类型为 `dict`/`Dict`/`Body`（或命名 `payload`/`body`/`data`…，**排除 `Depends(...)` 注入形参**）→ 扫函数体 `x.get("k")` / `x["k"]` |
| | 字段类型与必填 | `int(x)`/`float(x)`/`bool(x)` 转换、`or 默认值`、守卫语句 `not x` / `x is None` / `x == ''` / `x <= n` / `x not in (...)`（**仅认分支里真的 `raise` 的 if**；`x == "枚举值"` 这类纯分支不算必填） |
| 响应字段 | dict 字面量 | `return {...}` 的顶层键与值表达式类型推断 |
| | 局部变量回溯 | `r = {...}` / `r = helper(...)` / `r.append({...})` 后 `return r`，并合并 `r["k"] = ...` 形式的补充字段（覆盖「先组装再补字段」写法） |
| | 辅助函数内联 | `return _assembler(...)` → 回溯其 `return {...}` / `Response(...)`（一层，跨文件） |
| | DB 行 | `SELECT` 列名；`SELECT *` 时回落到 DDL 表列（含类型）。**必须数据流成立**：只有该查询确实赋值给被 return 的变量才用，否则退回「待补」，避免把旁支子查询当成响应结构 |
| | 文件 / 流 | `StreamingResponse` / `FileResponse` / `Response` + `media_type`（含经辅助函数间接返回的情形） |
| 数据模型 | 裸 DDL（SQLite / MySQL / PG） | `CREATE TABLE [IF NOT EXISTS]`（逐列解析名称/类型/PK/NOT NULL/UNIQUE/DEFAULT/CHECK/FK）、`CREATE INDEX`、`ALTER TABLE`；兼容**相邻字符串字面量拼接**的建表语句；`key` 这类恰好与 `KEY` 索引关键字同名的列不得被丢弃 |
| | 动态补列清单 | 常量名含 `ALTER`/`COLUMN`/`MIGRAT` 的模块级 `(表, 列, 列定义)` 三元组列表 → 并入目标表列集（标 `addedAt` 来源），并写入 `alterations`；与 DDL 已有的同名列自动去重 |
| | 同名表多处声明 | 核心文件优先；同类取列数最多的那一版（避免被 SQL 题示例库 / 夹具里的同名小表覆盖）；各声明的列数记入 `occurrences[].cols` |
| | SQLAlchemy / SQLModel / Django | `__tablename__`、`class X(Base/db.Model/models.Model/SQLModel)` |
| | JPA（Java/Kotlin） | `@Entity`、`@Table(name=...)` |
| 外部集成 | HTTP 客户端 | `httpx./requests./aiohttp./axios./got./urllib.request` 调用与 `AsyncClient/Session` 实例化 |
| | SDK 线索 | `openai / anthropic / boto3 / dashscope / zhipuai / ollama / tencentcloud / feishu / dingtalk` |
| | 消息队列 | `redis / pika / aio_pika / amqp / KafkaProducer / KafkaConsumer / celery / rocketmq / pulsar / nats / ActiveMQ / RabbitMQ / kombu` |
| | 外部进程 | `subprocess.run/Popen/...`、`child_process.exec/spawn/...` |
| | 端点线索 | URL 字面量 + `*_URL / _ENDPOINT / _HOST / _BASE / _URI` 配置键 |
| 依赖清单 | 见 `wiki_state.py` 的 `DEP_FILES` | requirements / pyproject / package.json / pom.xml / go.mod / Dockerfile / compose / start.sh 等 |

**命中不了怎么办**：该类别在页面上写"未能自动提取（技术栈未覆盖）"+ 待补清单，并在交付说明里明确告知用户。不要用通用推理硬凑接口或表结构。

### 字段结构的四个降级档

`api.md` 的请求 / 响应列按证据强度分档，**不要跳档编造**：

| 档 | 含义 | 页面写法 |
|----|------|----------|
| ✅ 已提取 | 有明确字段清单 | 直接列出字段名 / 类型 / 必填 |
| ◐ 结构已知 | 知道是对象 / 数组 / 文件，但字段清单不完整 | 写 `object（字段见 源位置）` 或 `array<object>` |
| ○ 仅签名 | 只有函数签名，无字段线索 | 写"见 `file:line` 签名"，不给字段 |
| ✗ 无 | 自动提取不到 | 写"待补：需人工确认" |

## 辅助文件判定

文件路径命中以下特征即视为**辅助文件**，其提取结果归入 `auxiliary*`，不进哈希、不进正文主表：

```
selftest* · test* · *test* · spec* · conftest* · mock* · seed* · sample* · demo* · fixture*
```

理由：这些文件里的表、端点、URL 多属测试夹具或演示数据（例如 `seed.py` 创建的是**示例考试库**而非系统表）。辅助内容仍会出现在 `extract` 输出中，供人判断。

> 若某个 `auxiliaryTables` 里的表实为业务表，在 `data-model.md` 中显式注明"疑为业务表，待确认"，不要静默丢弃。

## 输出结构

```jsonc
{
  "sourceFilesScanned": 79,
  "api": {
    "groups": [ { "prefix": "/api/exams", "file": "…/exams.py", "line": 32,
                  "framework": "fastapi/flask",
                  "endpoints": [ { "method": "POST", "path": "/api/exams",
                                   "handler": "create_exam", "signature": "…",
                                   "permissions": ["platform_admin","admin"],
                                   "authHint": true, "file": "…", "line": 47,
                                   "prefix": "/api/exams", "isAux": false,
                                   "bodyParam": "payload",
                                   "request": [ { "name": "name", "type": "string",
                                                  "required": true, "from": "payload.get(name)" },
                                                { "name": "question_ids", "type": "array",
                                                  "required": false, "from": "payload.get(question_ids)" } ],
                                   "response": { "kind": "object",           // object|array|stream|file|raw|redirect|none|scalar|unknown
                                                 "source": "_exam_public()  ·  backend/app/routers/exams.py",
                                                 "fields": [ { "name": "id", "type": "INTEGER", "from": "row[\"id\"]" } ] },
                                   "errors": [ { "status": 400, "detail": "考试名称不能为空" } ] } ] } ],
    "auxiliaryGroups": [ /* 测试 / mock 文件里的端点 */ ],
    "endpointCount": 63,
    "auxiliaryEndpointCount": 4
  },
  "dataModel": {
    "tables": [ { "name": "users",
                  "occurrences": [ { "file": "…/db.py", "line": 73, "kind": "ddl", "cols": 9 },
                                   { "file": "…/question_io.py", "line": 1162,
                                     "kind": "ddl", "cols": 2 } ],
                  "columns": [ { "name": "id", "type": "INTEGER", "constraints": ["PK","AUTO"] },
                               { "name": "username", "type": "TEXT", "constraints": ["NOT NULL","UNIQUE"] },
                               // 迁移补列另带来源位置，供页面标 †
                               { "name": "database_uid", "type": "TEXT", "constraints": [],
                                 "addedAt": "…/db.py:209" } ],
                  "addedColumns": [ /* 同 addedAt 那批，便于页面单列一节 */ ],
                  "auxOnly": false, "file": "…/db.py", "line": 73 } ],
    "auxiliaryTables": [ /* 仅出现在辅助文件里 */ ],
    "ormModels": [], "auxiliaryOrmModels": [],
    "indexes": [ { "name": "idx_submissions_lookup", "file": "…/db.py", "line": 228, "isAux": false } ],
    "alterations": [ { "table": "questions", "action": "ADD COLUMN", "column": "database_uid",
                       "file": "…/db.py", "line": 209, "isAux": false },
                     { "table": "saved_codes_v2", "action": "RENAME",
                       "file": "…/db.py", "line": 386, "isAux": false } ],
    "tableCount": 13, "auxiliaryTableCount": 5
  },
  "integrations": {
    "dependencies": [ { "file": "backend/requirements.txt", "content": "fastapi>=0.110\n…" } ],
    "httpCalls": [ { "lib": "httpx", "method": "", "kind": "init", "file": "…/ai.py", "line": 356, "snippet": "…" } ],
    "urls": [ { "url": "http://…", "key": "LLM_BASE_URL", "file": "…", "line": 74 } ],
    "messageQueue": [], "sdkHints": [], "externalProcesses": [],
    "nonGoals": [ { "change": "judge-concurrency-hardening", "text": "- 不引入消息队列…" } ],
    "usesMessageQueue": false
  }
}
```

`request[].required` 三态：`true` 必填 / `false` 可选 / `null` 未能判定（页面写"待确认"）。
`response.fields[].from` 记录字段的取值来源表达式，便于人工核对。
`response.unresolved = true` 表示结构已知但字段清单未解析出来。
`occurrences[].cols` 记录各处声明的列数，`columns[].addedAt` 标出迁移补列的来源位置。
`errors[].detail` 已还原为可读文案（`"%s 非法" % x` → `… 非法`）；整段是代码表达式时
（`str(exc)`、`"；".join(errors)`）写作 `（动态提示：<原表达式>）`，不臆造提示语。

## 哈希口径（增量判定用）

三个哈希都由**同一份提取结果**派生，保证「页面写的内容」与「触发条件」严格同源：

- `apiHash` ← `api.groups`（仅核心端点，含 `request` / `response` / `errors`）
- `dataModelHash` ← `tables`（含 `columns`）/ `ormModels` / `indexes` / `alterations`（仅核心表）
- `integrationHash` ← 依赖清单 + 核心的 httpCalls / urls / messageQueue / sdkHints / externalProcesses + `usesMessageQueue`

三条关键口径：

1. **哈希剥离行号**。格式化、加注释导致的行号整体位移**不会**触发重生成；端点增删、路径改名、权限变更、字段增删、类型或必填变化、表名或 DDL 语句变更**会**触发。
2. **只算核心**。辅助文件（测试 / mock / 种子示例）的改动不触发重生成。
3. **函数体内与字段声明无关的语句不算**。在 handler 里加日志、埋点、异常分支，只要不动 `payload.get(...)` 与 `return` 结构，`apiDirty` 保持 `False`。

跨页联动是**有意设计**：DDL 加列会同时触发 `dataModelDirty` 与 `apiDirty`——因为响应字段类型取自表列，接口页需要跟着更新。

若确需强制刷新某页，可在 `commit` 时显式带上对应开关（如 `--api`）。
