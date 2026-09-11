# 回归测试夹具

给 `tests/incremental_regression.py` 用的小号工程。它**不需要能跑起来**——只需要让 `wiki_state.py` 的声明类提取器看到真实项目里会出现的各种写法，从而把「增量触发口径」和「字段结构提取」钉死。

被测脚本把它整份复制到 `/tmp` 再改，**不会改动这里的任何文件**。

## 每个文件是为了压住哪个坑

| 位置 | 覆盖的写法 |
|------|-----------|
| `backend/app/db.py` | 裸 DDL、`CREATE INDEX`、`_ALTER_COLUMNS` 三元组动态补列、Python 相邻字符串字面量拼接的建表语句、`ALTER TABLE ... RENAME` 整表重建 |
| `backend/app/routers/exams.py` | 裸 `payload: dict` 请求体、`int()` 类型升级、`if not x` / `x <= 0` 守卫判必填、辅助函数 `_exam_public()` 内联出响应、同一函数多个 `HTTPException` |
| `backend/app/routers/accounts.py` | 多变量 `or` 守卫（`if not a or not b or not c`）、纯枚举分支 `x == "platform_admin"` **不得**算必填、`Depends()` 注入形参**不得**被当成请求体、核心文件里的同名小表 |
| `backend/app/routers/questions.py` | 局部变量字典字面量 + 事后 `resp["k"] = ...` 补字段、`Response(media_type=...)` 二进制下载 |
| `backend/app/routers/databases.py` | `brief = _row_brief(row)` 变量经辅助函数组装 + 事后补字段 |
| `backend/app/routers/ai.py` | `async def` 处理函数（漏了会把字段整段丢掉） |
| `backend/app/routers/student.py` | `out.append({...})` 循环组装数组，且函数体里另有一条 `SELECT *` **不得**盖掉它 |
| `backend/app/ai_client.py` | 第三方 HTTP 客户端实例化（`httpx.AsyncClient(...)`）与 base_url 常量 |
| `backend/app/main.py` | `subprocess` 外部进程探测（外部工具链依赖的事实源） |
| `backend/selftest_api.py` | 名字含 `selftest` 的辅助文件：其建表与路由**必须**被排除在核心提取与哈希之外 |
| `openspec/` | 3 个已归档变更 + 1 个进行中变更（各带 `design.md`）、3 份能力规格 |

## 有意留下的「不整洁」

夹具里几处刻意的重复与降级，都是为了让断言能验到边界，**不是疏漏**：

- `users` 表被声明了 4 次，列数分别是 9 / 3 / 2 / 2。取列数最多的核心声明（9 列）才是正确行为。
- `ai_generate_jobs.kind` 既在 DDL 里、又在补列清单里。补列时**必须**跳过已存在的列。
- `submissions.lang` 只在补列清单里、不在 DDL 里。它应当带 `addedAt` 来源位置出现在有效列集中。
- `accounts.py` 的 `_EXAMPLE_DDL` 是给 SQL 题预览用的示例库，与平台业务表同名但不是同一张表。
