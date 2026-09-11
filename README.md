# openspec-wiki

基于 [OpenSpec](https://github.com/Fission-AI/OpenSpec) 规格文档与代码声明，为项目生成并增量维护 Wiki 知识库。类比 Qoder 的 Repo Wiki / DeepWiki，但事实源是**规格文档 + 声明类提取**，不做代码反推——spec 本身就是半成品 Wiki，代码只补规格里没有的接口、数据与外部依赖。

## 用途

把 `openspec/` 目录的规格文档、以及代码里的**声明类信息**（路由、请求/响应字段、DDL、依赖清单、调用点）改写成给人读、也给 AI Agent 读的 Wiki，输出到项目下的 `wiki/` 目录（不存在则新建）：

```
wiki/
├── README.md              # 总览：项目简介 + 文档地图 + 能力地图 + 进行中/最近变更
├── architecture.md        # 系统架构：技术栈、分层、能力依赖、关键流程、部署、约束、待补
├── api.md                 # 接口清单：分组端点表（含请求字段/响应结构）+ 错误约定 + curl 示例
├── data-model.md          # 数据库设计：业务设计（实体/ER/生命周期）+ 物理设计（表/列/类型/约束/索引）
├── integrations.md        # 外部集成：第三方接口、消息队列、外部进程、运行时依赖、非目标
├── decisions.md           # 架构决策记录（ADR）：背景/决策/否决方案/风险/待决问题
├── glossary.md            # 术语表
├── specs/<capability>.md  # 每个能力一页（需求契约 + 行为场景）
├── changelog.md           # 变更日志（按归档变更倒序）
└── .wiki-manifest.json    # 同步账本（脚本维护，禁止手改）
```

Wiki 是 `openspec/` 与源码的只读消费方，不修改任何被读取的文件；产物为仓库内 Markdown，随 Git 推送即可团队共享，也可直接作为 Agent 的检索语料。

## 使用方法

对 WorkBuddy：直接说「用 openspec-wiki 给 `<项目路径>` 生成 wiki」或「更新 `<项目路径>` 的 wiki」即可，Agent 会加载本技能执行。

核心输入只有一个：**项目目录的绝对路径**（目录下必须存在 `openspec/`）。技能内部按四步工作流执行：

1. **plan** — 运行 `scripts/wiki_state.py plan <项目路径>` 获取同步计划（全量 or 增量、待生成页面、待同步变更与决策）；
2. **生成** — 按 `references/templates.md` 模板只写计划列出的页面；接口 / 数据 / 集成三页先用 `extract` 取现成提取结果，不重读源码；
3. **commit** — 运行 `wiki_state.py commit` 把本次实际处理的内容记回账本；
4. **复核** — 重跑 plan，确认无遗漏后汇报（含降级为「待补」的内容）。

也可单独调用脚本：

```bash
python3 <skill_dir>/scripts/wiki_state.py plan    <项目路径>            # 输出 JSON 同步计划
python3 <skill_dir>/scripts/wiki_state.py extract <项目路径>            # 输出声明类提取结果（JSON）
python3 <skill_dir>/scripts/wiki_state.py commit  <项目路径> \
  --caps a,b --change-ids x,y --decisions x,y --overview \
  --architecture --glossary --api --data-model --integrations           # 生成完成后记账
```

## 基本原理

核心是一条「**规划 → 生成 → 记账 → 复核**」的流水线，增量判断由确定性脚本完成，LLM 只负责内容改写：

| 映射 | 事实源 | Wiki 产物 |
|------|--------|-----------|
| 项目总览 | `openspec/project.md` 或项目 README | `wiki/README.md` |
| 能力文档 | `openspec/specs/<cap>/spec.md` | `wiki/specs/<cap>.md` |
| 变更记录 | `openspec/changes/archive/*/proposal.md` | `wiki/changelog.md` |
| 架构决策 | `openspec/changes/archive/*/design.md` | `wiki/decisions.md` |
| 架构与约束 | 总览源 + 目录结构 + 依赖清单 + design.md 约束节 | `wiki/architecture.md` |
| 接口清单 | 路由装饰器 / 函数签名 / 权限依赖 + `payload.get(...)` 请求字段 + `return` 响应结构 | `wiki/api.md` |
| 数据库设计 | DDL（含列名/类型/约束）/ ORM 模型 / 迁移语句 | `wiki/data-model.md` |
| 外部集成 | 依赖清单 + 调用点 + URL/配置键 + 非目标 | `wiki/integrations.md` |

**增量更新不靠全量内容比对**，而是靠账本 `wiki/.wiki-manifest.json` 记录的九类状态：`syncedChanges`（已写入 changelog 的变更 ID）、`specs`（各能力 spec 哈希）、`decisions`（各 design.md 哈希）、`overviewHash`、`architectureHash`、`glossaryHash`、`apiHash`、`dataModelHash`、`integrationHash`。重跑时只比 sha256，毫秒级判定哪些页面真的过期。

三条关键口径：

- **哈希剥离行号** —— 格式化、加注释导致的行号位移不触发重生成；声明增删改才触发；
- **只算核心** —— 测试 / mock / 种子示例文件里的表、端点、URL 归入辅助信息，不参与哈希；
- **不算实现细节** —— handler 里加日志、埋点、异常分支不触发；只有字段取值与 `return` 结构变化才算。

跨页联动是有意设计：DDL 加列会同时触发 `dataModelDirty` 与 `apiDirty`（响应字段类型取自表列）。

因此每次更新，LLM 只需读"确定过期"的少数文件；已同步的变更连 `proposal.md` 都不必打开。

## 读取边界

代码侧只做**声明类提取**，不解析实现逻辑：

| 读 | 不读 |
|----|------|
| 路由装饰器、函数签名、权限依赖声明 | 函数体的业务实现逻辑（分支、循环、算法、副作用） |
| 函数体内的字段声明：`payload.get("x")`、返回结构（dict 字面量 / 辅助函数 return / SELECT 列） | 调用链追踪、跨模块数据流 |
| DDL 语句（含列名 / 类型 / 约束）、ORM 模型声明、迁移语句 | 运行时数据、数据库文件内容 |
| HTTP 客户端调用点、URL 与配置键字面量 | 动态拼接的地址 |
| 依赖清单文件内容 | 第三方库源码 |

已覆盖 FastAPI / Flask / Express / Koa / Spring 路由、裸 dict 与 Pydantic 风格请求体、dict 字面量 / 辅助函数 / DB 行三类响应结构、裸 DDL / SQLAlchemy / Django / JPA 模型、httpx / requests / axios 调用、redis / kafka / rabbitmq / celery 等 MQ 客户端。**技术栈未命中时降级为「待补」占位并明确告知，不臆造内容。** 详见 `references/extractors.md`。

## 目录结构

```
openspec-wiki/
├── SKILL.md                  # 技能说明与四步工作流（Agent 执行依据）
├── README.md                 # 本文件
├── scripts/wiki_state.py     # 确定性账本与提取工具（纯 Python 标准库，无第三方依赖）
├── references/
│   ├── templates.md          # 9 类页面的模板与写作红线
│   └── extractors.md         # 声明类提取的模式目录、边界与哈希口径
└── tests/
    └── incremental_regression.py   # 51 条断言：九类哈希的增量触发口径 + 字段结构提取准确性
```

### 回归测试

改过 `wiki_state.py` 后跑一遍（把夹具项目路径作为唯一参数，默认取一个含 `openspec/` 的样例项目）：

```bash
python3 <skill_dir>/tests/incremental_regression.py [样例项目路径]
```

断言覆盖：全量 / 增量模式切换、行号整体位移与辅助文件改动**不得**触发、新增路由 / 建表语句加列 / 引入 MQ **必须**触发、DDL 加列联动接口页、请求字段名·类型·必填准确性（含多变量 `not` 守卫与枚举分支的区分）、响应结构回溯（dict 字面量 / 局部变量 / `helper()` / `append` / `SELECT` 兜底 / 二进制下载）、DDL 列抽取保真（`key` 列、字符串拼接建表、同名小表不得覆盖核心表、动态补列清单）。
