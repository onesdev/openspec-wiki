---
name: openspec-wiki
description: 基于 OpenSpec 规格文档为项目生成并增量维护 Wiki 知识库。输入项目目录路径（须含 openspec/），在项目下 wiki/ 目录输出总览、能力文档与变更日志；通过 .wiki-manifest.json 账本记录已同步的变更列表，配合 spec 文件 sha256 漂移检测实现精准增量更新，只重生成受影响的页面。当用户要求"生成项目 wiki"、"更新 wiki"、"把 openspec 文档同步成 wiki"时使用此技能。
agent_created: true
---

# openspec-wiki：从 OpenSpec 规格生成并增量维护项目 Wiki

## 目标与产物

把 `openspec/` 里的规格文档（specs、changes/archive）改写成给人读、也给 AI Agent 读的 Wiki，输出到 `<项目>/wiki/`（不存在则新建）：

```
wiki/
├── README.md              # 总览：项目简介 + 能力地图 + 进行中变更 + 最近变更
├── specs/<capability>.md  # 每个能力一页（需求契约 + 行为场景）
├── changelog.md           # 变更日志（按归档变更倒序追加）
└── .wiki-manifest.json    # 同步账本（脚本维护，禁止手改）
```

## 输入与前置检查

1. 输入：项目目录的**绝对路径**（用户会直接给出；若未给出则询问）。
2. 校验：目录下必须存在 `openspec/`，否则报错终止。
3. 不修改、不删除 `openspec/` 内的任何文件；Wiki 是只读消费方。

## 工作流程（四步，严格按序）

### 第 1 步：获取同步计划

运行随技能附带的确定性脚本（脚本所在目录即本 SKILL.md 所在目录，下称 `<skill_dir>`）：

```bash
python3 <skill_dir>/scripts/wiki_state.py plan <项目路径>
```

返回 JSON，关键字段：

| 字段 | 含义 |
|------|------|
| `mode` | `full`（首次/无账本）或 `incremental` |
| `capabilitiesToGenerate` | 本次需要（重）生成的能力页 |
| `pendingChanges` | 尚未同步进 changelog 的已归档变更 |
| `activeChanges` | 进行中变更（仅用于 README"进行中"小节，不记入账本） |
| `driftedCapabilities` | spec 文件哈希与账本不符（被绕过流程直改）的能力 |
| `capabilitiesRemoved` | 已从 specs 删除、需从 wiki 摘除的能力 |
| `overviewDirty` | 总览事实源（openspec/project.md 或项目 README.md / config.yaml）变化 |

计划为空（无待生成能力、无 pending 变更、总览干净）时，直接告知"Wiki 已是最新"并结束。

### 第 2 步：按模式生成内容

**先读 `references/templates.md` 获取三种页面的模板与写作规范，再动手。**

**full 模式（首次）**：
1. 读总览事实源：`openspec/project.md`（优先）或项目 `README.md`，以及 `openspec/config.yaml` 的 `context`。
2. 读 `openspec/specs/*/spec.md` 全部能力，逐页生成 `wiki/specs/<capability>.md`。
3. 读全部归档变更的 `proposal.md`（重点取 Why / What Changes / Capabilities），生成 `wiki/changelog.md`。
4. 生成 `wiki/README.md`（能力地图表格覆盖所有能力）。

**incremental 模式**——只动计划列出的内容，其余页面一个字都不碰：
- `capabilitiesToGenerate` 中的每个能力：**以当前 `openspec/specs/<cap>/spec.md` 为唯一事实源重写该页**（pending 变更的 delta 只用来"定位哪些页过期"，不作为内容来源——归档时 delta 已合并进 specs）。
- `pendingChanges`：逐个读其 `proposal.md`，按模板向 `changelog.md` **追加**条目（倒序插在最上）。
- `capabilitiesRemoved`：删除对应 `wiki/specs/<cap>.md`，并在 changelog 追加一条"能力移除"记录。
- `overviewDirty`：重写 `README.md`（能力地图全量刷新，进行中/最近变更小节同步刷新）。
- `activeChanges`：刷新 README"进行中变更"小节。

### 第 3 步：记账（commit）

生成全部落盘后，把本次实际处理的内容写回账本：

```bash
python3 <skill_dir>/scripts/wiki_state.py commit <项目路径> \
  --caps <本次生成的能力,逗号分隔> \
  --change-ids <本次写入changelog的变更ID,逗号分隔> \
  --remove-caps <已删除页面的能力,逗号分隔> \
  --overview   # 仅当本次更新了 README.md 时加
```

必须与第 2 步实际完成的内容严格一致：没生成的能力不报 `--caps`，没追加的变更不报 `--change-ids`。

### 第 4 步：复核与汇报

重跑一次 `plan`，确认 `capabilitiesToGenerate`、`pendingChanges`、`driftedCapabilities` 均为空且 `overviewDirty=false`。向用户汇报：本次模式、新建/更新/删除了哪些页面、同步了哪些变更、Wiki 位置。

## 增量机制（为什么不用每次对比 spec 内容）

账本 `.wiki-manifest.json` 由脚本维护，记录三类状态：
1. **syncedChanges**：已写入 changelog 的变更 ID 及其涉及能力——新归档变更 = 账本里查不到的 archive 目录，直接增量处理；
2. **specs 哈希**：每个已生成能力页对应 spec.md 的 sha256——重跑时只比哈希（毫秒级），即可发现"绕过 OpenSpec 流程直改 spec"造成的漂移；
3. **overviewHash**：总览事实源哈希——决定 README 是否需要刷新。

因此增量更新时 LLM 只需读"确定过期"的少数文件，无需全量比对内容。

## 生成规范（要点）

- 语言：简体中文；保留规格中的 SHALL/MUST 等关键词语义。
- 改写不是复制：Purpose → "这是什么"（1-3 句）；Requirement → 契约要点 + 场景表；不逐字照搬长段落。
- 每页头部注明源规格相对路径与"由 openspec-wiki 生成"；正文链接回源文件与其他能力页。
- changelog 条目必须含：日期、变更 ID、一句话 Why、影响能力（链接到 wiki 页）、指向 openspec 归档 proposal 的相对链接。
- 只写 openspec 里有的内容；需要代码实现细节时可在对应能力页追加"实现指引"小节，但须注明来源文件。

## 注意事项

- `plan`/`commit` 之间不要穿插其他项目操作；commit 失败时不得谎报完成。
- 若用户要求调整 Wiki 风格/结构，先改模板再重生成受影响页面，并保持账本一致。
- 多项目场景：对每个项目路径独立执行上述四步，账本互不影响。
