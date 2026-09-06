# openspec-wiki 页面模板与写作规范

生成任何 Wiki 页面前先读本文件。所有页面：简体中文；头部用引用行注明生成来源；不虚构 openspec 里没有的内容。

## 1. 能力页 `wiki/specs/<capability>.md`

```markdown
# <能力名（中文标题，取自 Purpose 概括）>

> 源规格：`openspec/specs/<capability>/spec.md` · 由 openspec-wiki 生成 · 请勿手改，改规格后重新运行同步

## 这是什么

<把 spec 的 ## Purpose 改写成 1-3 句：这个能力负责什么、边界在哪、和哪些能力相关。
 相关能力用 [能力名](<capability>.md) 链接。>

## 需求契约

<每个 ### Requirement 一小节，保留原需求标题与 SHALL/MUST 语义：>

### <Requirement 原标题>

- <契约要点：用 1-2 句说清"系统必须保证什么"，保留 SHALL/MUST/ numbers / 常量。>

| 场景 | WHEN | THEN |
|------|------|------|
| <场景名> | <触发条件> | <预期行为> |

<场景多于 4 个时可只列关键场景并注明"更多场景见源规格"。>
```

写作红线：
- 需求标题不改写（便于和 spec 对照）。
- 数字、常量、阈值、角色名、文件名一律原样保留。
- 场景表是"行为示例"，不是全文翻译；语义不得增删。

## 2. 变更日志 `wiki/changelog.md`

文件头：

```markdown
# 变更日志

> 由 openspec-wiki 从 `openspec/changes/archive/` 生成 · 倒序 · 请勿手改

## 进行中

<有 openspec/changes/* 活跃变更时逐条列出：`- <change-id>：<proposal 的 Why 一句话>（进行中，归档后自动转正）`；无则写"暂无"。此节不记入账本，每次同步时刷新。>
```

每条已归档变更（**倒序插在"进行中"节之后、旧条目之前**）：

```markdown
## <YYYY-MM-DD> <change-id>

- **为什么**：<proposal Why 的 1-2 句概括>
- **改了什么**：<What Changes 的要点，1-3 条；无则省略此行>
- **影响能力**：<每个能力一个链接，如 [judge-grading-pipeline](specs/judge-grading-pipeline.md)，多个用顿号分隔>
- 详情：[`openspec/changes/archive/<目录名>/proposal.md`](../openspec/changes/archive/<目录名>/proposal.md)
```

能力被整体移除（capabilitiesRemoved）时追加特殊条目：

```markdown
## <同步日期> （能力移除）

- **<capability>** 已从规格中移除，对应 Wiki 页面已删除。来源变更：<change-id>
```

## 3. 总览页 `wiki/README.md`

```markdown
# <项目名> Wiki

> 由 openspec-wiki 基于 `openspec/` 规格文档生成 · 请勿手改，改规格后重新运行同步

<项目简介：来自 openspec/project.md 或项目 README.md 的开头部分，2-4 句。
 config.yaml 的 context（技术栈、约定）存在时并入一段"技术栈与约定"。>

## 能力地图

| 能力 | 说明 | 文档 |
|------|------|------|
| <capability> | <Purpose 的一句话概括> | [查看](specs/<capability>.md) |

<全部能力都要在表里，按字母序。>

## 进行中变更

<同 changelog 的"进行中"节；无则写"暂无"。>

## 最近变更

<最近 5 条归档变更：`- <日期> [<change-id>](changelog.md#<日期>-<change-id>)：<一句话>`；链接锚点不必精确，统一链到 changelog.md 即可。>
```

## 4. 改写质量自检（生成后逐页过一遍）

1. 每个 Requirement 都有对应小节，标题未改名。
2. 场景表 WHEN/THEN 无语义增删；数字/常量/角色名未变。
3. 页内链接（能力互链、changelog→specs、README→specs）全部有效。
4. 头部来源行存在且路径正确。
