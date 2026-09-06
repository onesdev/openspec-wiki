# openspec-wiki

基于 [OpenSpec](https://github.com/Fission-AI/OpenSpec) 规格文档，为项目生成并增量维护 Wiki 知识库。类比 Qoder 的 Repo Wiki / DeepWiki，但事实源是**规格文档而非代码反推**——spec 本身就是半成品 Wiki。

## 用途

把 `openspec/` 目录里的规格文档改写成给人读、也给 AI Agent 读的 Wiki，输出到项目下的 `wiki/` 目录（不存在则新建）：

```
wiki/
├── README.md              # 总览：项目简介 + 能力地图 + 进行中/最近变更
├── specs/<capability>.md  # 每个能力一页（需求契约 + 行为场景）
├── changelog.md           # 变更日志（按归档变更倒序追加）
└── .wiki-manifest.json    # 同步账本（脚本维护，禁止手改）
```

Wiki 是 `openspec/` 的只读消费方，不修改、不删除规格文档；产物为仓库内 Markdown，随 Git 推送即可团队共享，也可直接作为 Agent 的检索语料。

## 使用方法

对 WorkBuddy：直接说「用 openspec-wiki 给 `<项目路径>` 生成 wiki」或「更新 `<项目路径>` 的 wiki」即可，Agent 会加载本技能执行。

核心输入只有一个：**项目目录的绝对路径**（目录下必须存在 `openspec/`）。技能内部按四步工作流执行：

1. **plan** — 运行 `scripts/wiki_state.py plan <项目路径>` 获取同步计划（全量 or 增量、待生成页面、待同步变更）；
2. **生成** — 按 `references/templates.md` 模板，只写计划列出的页面；
3. **commit** — 运行 `wiki_state.py commit` 把本次实际处理的内容记回账本；
4. **复核** — 重跑 plan，确认无遗漏后汇报。

也可单独调用脚本获取计划 / 记账：

```bash
python3 <skill_dir>/scripts/wiki_state.py plan   <项目路径>   # 输出 JSON 同步计划
python3 <skill_dir>/scripts/wiki_state.py commit <项目路径> \
  --caps <能力1,能力2> --change-ids <变更ID> --overview      # 生成完成后记账
```

## 基本原理

核心是一条「**规划 → 生成 → 记账 → 复核**」的流水线，增量判断由确定性脚本完成，LLM 只负责内容改写：

| 映射 | OpenSpec 源 | Wiki 产物 |
|------|-------------|-----------|
| 项目总览 | `openspec/project.md`（或项目 README） | `wiki/README.md` |
| 能力文档 | `openspec/specs/<cap>/spec.md` | `wiki/specs/<cap>.md` |
| 变更记录 | `openspec/changes/archive/*/proposal.md` | `wiki/changelog.md` |

**增量更新不靠全量内容比对**，而是靠账本 `wiki/.wiki-manifest.json` 记录的三类状态：

1. **syncedChanges** — 已写入 changelog 的变更 ID 清单。新归档变更 = 账本里查不到的 archive 目录，直接增量处理，不重读任何已同步的 spec；
2. **specs sha256** — 每个已生成能力页对应 spec 的哈希。重跑时毫秒级比哈希，兜底捕获"绕过 OpenSpec 流程直改 spec"造成的漂移；
3. **overviewHash** — 总览事实源哈希，变化才刷新 README。

因此每次更新，LLM 只需读"确定过期"的少数文件：以当前 `specs/<cap>/spec.md` 为唯一事实源重写受影响页面，向 changelog 追加新变更条目，其余页面一个字不动。

## 目录结构

```
openspec-wiki/
├── SKILL.md                # 技能说明与四步工作流（Agent 执行依据）
├── README.md               # 本文件
├── scripts/wiki_state.py   # 确定性账本工具（纯 Python 标准库，无第三方依赖）
└── references/templates.md # 总览页 / 能力页 / changelog 模板与写作规范
```
