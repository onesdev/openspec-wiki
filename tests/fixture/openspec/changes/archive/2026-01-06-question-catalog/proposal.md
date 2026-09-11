# 题库浏览与详情提案

## Change ID

question-catalog

## Why

题库此前只能从「考试组卷」入口间接看到，管理员缺少一个独立的题库视图，也无法从题目跳到它引用的 SQL 题库。本变更补齐题库的浏览、详情与资产下载三条路径。

## What Changes

- 新增 `question-catalog` 能力与 `GET /api/questions`、`GET /api/questions/{id}`。
- 题目详情返回 `database_uid` 与 `database_name`：前者是题目引用的题库标识，后者由一次附加查询补全。
- 新增 `GET /api/questions/template-pack`，以 `application/zip` 流式返回出题模板包。
- 非目标：不在题库内做全文检索；不提供题目的批量导出；不引入题目标签体系。

## Capabilities

- question-catalog（ADDED：题库列表、题目详情与关联题库、内置资产下载）

## Impact

- 后端：`backend/app/routers/questions.py`、`backend/app/db.py`（`questions.database_uid` 补列）
- 兼容性：`questions` 表补列对存量库由迁移清单保证，无破坏性变更
