---
name: openspec-wiki
description: 基于 OpenSpec 规格文档与代码声明为项目生成并增量维护 Wiki 知识库。输入项目目录路径（须含 openspec/），在项目下 wiki/ 目录输出总览、系统架构、接口清单（含请求/响应字段结构）、数据库设计（含表列类型与约束）、外部集成、架构决策、术语表、变更日志与各能力文档；通过 .wiki-manifest.json 账本记录已同步内容与多个事实源哈希实现精准增量更新，只重生成受影响的页面。当用户要求"生成项目 wiki"、"更新 wiki"、"把 openspec 文档同步成 wiki"、"生成接口清单 / 数据库设计文档 / 架构文档"时使用此技能。
agent_created: true
---

# openspec-wiki：从 OpenSpec 规格与代码声明生成并增量维护项目 Wiki

## 目标与产物

把 `openspec/` 的规格文档与代码中的**声明类信息**改写成给人读、也给 AI Agent 读的 Wiki，输出到 `<项目>/wiki/`（不存在则新建）：

```
wiki/
├── README.md              # 总览：项目简介 + 文档地图 + 能力地图 + 进行中/最近变更
├── architecture.md        # 系统架构：技术栈、分层、能力依赖、关键流程、部署、约束、待补
├── api.md                 # 接口清单：按路由前缀分组的端点表（方法/路径/用途/权限/请求字段/响应结构）+ curl 示例
├── data-model.md          # 数据库设计：业务设计（实体/ER/生命周期）+ 物理设计（表/列/类型/约束/索引/迁移）
├── integrations.md        # 外部集成：第三方接口、消息队列、外部进程、运行时依赖、非目标
├── decisions.md           # 架构决策记录（ADR）：背景/决策/否决方案/风险/待决问题
├── glossary.md            # 术语表
├── specs/<capability>.md  # 每个能力一页（需求契约 + 行为场景）
├── changelog.md           # 变更日志（按归档变更倒序）
└── .wiki-manifest.json    # 同步账本（脚本维护，禁止手改）
```

## 输入与前置检查

1. 输入：项目目录的**绝对路径**（用户会直接给出；若未给出则询问）。
2. 校验：目录下必须存在 `openspec/`，否则报错终止。
3. 不修改、不删除 `openspec/` 内的任何文件；Wiki 是只读消费方。
4. 代码侧只做**声明类提取**（见「读取边界」），不改动任何源码。

## 工作流程（四步，严格按序）

### 第 1 步：获取同步计划

```bash
python3 <skill_dir>/scripts/wiki_state.py plan <项目路径>
```

返回 JSON，关键字段：

| 字段 | 含义 |
|------|------|
| `mode` | `full`（首次/无账本）或 `incremental` |
| `artifactsToGenerate` | 本次要写的页面清单（**只写这里列出的**） |
| `capabilitiesToGenerate` | 需要（重）生成的能力页 |
| `pendingChanges` | 尚未同步进 changelog 的已归档变更 |
| `pendingDecisions` | 有 design.md 但尚未提取进 decisions.md 的变更（含 `reason`：`未提取` / `design.md 已变更`） |
| `activeChanges` | 进行中变更（仅用于 README「进行中」小节，不记入账本） |
| `driftedCapabilities` | spec 哈希与账本不符（被绕过流程直改）的能力 |
| `capabilitiesRemoved` | 已从 specs 删除、需从 wiki 摘除的能力 |
| `overviewDirty` / `readmeDirty` | 总览事实源变化 / README 需刷新（含新增页面导致文档地图变化） |
| `architectureDirty` | 架构页事实源组合变化 |
| `glossaryDirty` | 术语表事实源变化 |
| `apiDirty` / `dataModelDirty` / `integrationDirty` | 三类声明提取结果变化 |
| `stats` | 计数摘要（能力数、端点数、表数、扫描文件数等） |

计划全空（无待生成页面、无 pending 变更与决策）时，直接告知「Wiki 已是最新」并结束。

### 第 2 步：按模式生成内容

**先读 `references/templates.md`（页面模板与写作红线）；涉及接口 / 数据 / 集成三页时，同时读 `references/extractors.md`（提取口径与降级规则）。**

**声明类提取**——生成接口、数据、集成三页前先取现成提取结果，**不要重新读源码**：

```bash
python3 <skill_dir>/scripts/wiki_state.py extract <项目路径> [--only api,dataModel,integrations]
```

**full 模式（首次）**——按下列顺序生成全部页面：

1. 读总览事实源：`openspec/project.md`（优先）或项目 `README.md`，以及 `openspec/config.yaml` 的 `context`。
2. 读 `openspec/specs/*/spec.md` 全部能力 → 逐页生成 `wiki/specs/<capability>.md`。
3. 读全部归档变更的 `proposal.md`（Why / What Changes / Capabilities）→ 生成 `wiki/changelog.md`。
4. 读全部 `design.md` 的 Decisions / Risks / Open Questions → 生成 `wiki/decisions.md`。
5. 由 specs 提取术语 → 生成 `wiki/glossary.md`。
6. 结合总览源、目录结构、依赖清单、能力集合、design.md 约束节 → 生成 `wiki/architecture.md`（含「待补」节）。
7. 由 `extract` 输出 → 生成 `wiki/api.md`（端点表含请求字段 / 响应结构 / 错误约定列）、`wiki/data-model.md`（表清单 + 逐列类型与约束）、`wiki/integrations.md`。
8. 生成 `wiki/README.md`（文档地图 + 能力地图 + 进行中 / 最近变更）。

**incremental 模式**——只动 `artifactsToGenerate` 列出的内容，其余页面一个字都不碰：

- 能力页：**以当前 `openspec/specs/<cap>/spec.md` 为唯一事实源重写**（pending 变更的 delta 只用于定位哪些页过期，不作为内容来源——归档时 delta 已合并进 specs）。
- `pendingChanges`：逐个读 `proposal.md`，按模板向 `changelog.md` **倒序追加**。
- `pendingDecisions`：逐个读 `design.md`，按模板向 `decisions.md` **倒序追加**。
- `capabilitiesRemoved`：删除 `wiki/specs/<cap>.md`，并在 changelog 追加一条"能力移除"记录。
- `api.md` / `data-model.md` / `integrations.md`：重新跑 `extract`，按新结果重写对应页面（保留仍有效的人工补充段落）。
- `architecture.md` / `glossary.md` / `README.md`：按各自 dirty 标志重写。

### 第 3 步：记账（commit）

生成全部落盘后，把**本次实际处理**的内容写回账本：

```bash
python3 <skill_dir>/scripts/wiki_state.py commit <项目路径> \
  --caps <本次生成的能力,逗号分隔> \
  --change-ids <本次写入 changelog 的变更ID,逗号分隔> \
  --decisions <本次写入 decisions 的变更ID,逗号分隔> \
  --remove-caps <已删除页面的能力,逗号分隔> \
  --overview --architecture --glossary --api --data-model --integrations
  # 末尾六个开关只加本次确实更新了的页面
```

必须与第 2 步实际完成的内容严格一致：没写的能力不报 `--caps`，没追加的变更不报 `--change-ids` / `--decisions`。

### 第 4 步：复核与汇报

重跑一次 `plan`，确认 `capabilitiesToGenerate`、`pendingChanges`、`pendingDecisions` 与各 dirty 标志均为空。向用户汇报：本次模式、新建 / 更新 / 删除了哪些页面、同步了哪些变更与决策、Wiki 位置，以及**哪些内容降级为「待补」**（如技术栈未覆盖导致接口或表结构未提取）。

## 读取边界（代码侧）

| 读 | 不读 |
|----|------|
| 路由装饰器、函数签名、权限依赖声明 | 函数体的业务实现逻辑（分支、循环、算法、副作用） |
| 函数体内的**字段声明**：请求体取值 `payload.get("x")`、返回结构（dict 字面量 / 辅助函数 return / `SELECT` 列） | 调用链追踪、跨模块数据流 |
| DDL 语句（含**列名 / 类型 / 约束**）、ORM 模型声明、迁移语句 | 运行时数据、数据库文件内容 |
| HTTP 客户端调用点、URL 与配置键字面量 | 动态拼接的地址 |
| 依赖清单文件内容 | 第三方库源码 |
| `design.md` 的约束 / Non-Goals 节 | `proposal.md` 的实现任务细节 |

字段结构的提取口径与降级档位（✅已提取 / ◐结构已知 / ○仅签名 / ✗待补）见 `references/extractors.md`。
细节与各技术栈的识别方式同样见 `references/extractors.md`。
改动 `scripts/wiki_state.py` 后请跑 `python3 <skill_dir>/tests/incremental_regression.py`（56 条断言，用技能自带的 `tests/fixture/` 最小工程，不依赖任何外部项目；覆盖九类哈希的触发口径与字段结构提取准确性）。

## 增量机制（为什么不用每次对比内容）

账本 `.wiki-manifest.json` 由脚本维护，记录以下状态（全部只比 sha256）：

| 账本项 | 覆盖对象 | 变化即触发 |
|--------|----------|-----------|
| `syncedChanges` | 已写入 changelog 的变更 ID | changelog 追加 |
| `specs` | 各能力 `spec.md` 哈希 | 该能力页重写（含绕过流程直改 spec 的漂移） |
| `decisions` | 各变更 `design.md` 哈希 | decisions.md 追加 |
| `overviewHash` | 总览事实源（project.md / README + config.yaml） | README 刷新 |
| `architectureHash` | 总览源 + 目录结构 + 依赖文件 + 能力集合 + 各 design.md 的约束 / 非目标节 | architecture.md 重写 |
| `glossaryHash` | 能力名 + 各 spec 的 Purpose + 需求标题 + 行内代码标识符 | glossary.md 重写 |
| `apiHash` | 路由 / 权限 / 请求字段 / 响应结构 / 错误约定的提取结果（核心） | api.md 重写 |
| `dataModelHash` | DDL（含列名 / 类型 / 约束）/ ORM 声明的提取结果（核心） | data-model.md 重写 |
| `integrationHash` | 依赖清单 + 外部调用点 + URL / 配置键 + MQ 线索 + 非目标 | integrations.md 重写 |

三条关键口径：

1. **哈希剥离行号**：格式化、加注释不触发；声明增删改才触发。
2. **只算核心**：测试 / mock / 种子示例文件不触发。
3. **不算实现细节**：handler 里加日志、埋点、异常分支，只要不动字段取值与 `return` 结构，不触发（回归测试已覆盖）。

跨页联动是**有意设计**：DDL 加列会同时触发 `dataModelDirty` 与 `apiDirty`——响应字段类型取自表列，接口页需跟着更新。

## 生成规范（要点）

- 语言：简体中文；保留规格中 SHALL/MUST 等关键词语义。
- 改写不是复制：Purpose → "这是什么"（1-3 句）；Requirement → 契约要点 + 场景表；不逐字照搬长段落。
- **页面按来源标注**：由规格改写的页面标 `源规格：openspec/...`；由代码声明提取的页面标到 `源位置`（文件:行）；`architecture.md` 这类综合推断页**逐节**标注来源。
- changelog 条目必须含：日期、变更 ID、一句话 Why、影响能力（链接）、指向归档 proposal 的相对链接。
- **禁止编造**：推不出来的内容（性能指标、容量规划、外部系统边界）写进 `architecture.md` 的「待补」节，明确标注"需人工输入"。
- **字段结构必须标注档位**：由代码提取的字段逐行标 `源位置`；`required` 为 `null` 的字段注明"待确认"；未解析出字段的响应标 `◐ 结构已知` 或 `○ 仅签名（file:line）`，**不得臆造字段名或类型**。
- **空集必须显式记录**：如项目未使用消息队列时，`integrations.md` 仍保留该节并写明"未使用"及 design.md 中的依据。

## 注意事项

- `plan` / `commit` 之间不要穿插其他项目操作；commit 失败时不得谎报完成。
- 若用户要求调整 Wiki 风格 / 结构，先改模板再重生成受影响页面，并保持账本一致。
- 多项目场景：对每个项目路径独立执行上述四步，账本互不影响。
- 技术栈未覆盖时（非上述框架），对应页面降级为待补占位，**并在汇报中明确告知**，不得静默留空。
