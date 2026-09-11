# 操作审计流水提案

## Change ID

add-audit-trail

## Why

账号管理与题库编辑目前没有任何留痕：谁在什么时候改了哪个账号的角色、谁删了哪道题，事后只能翻应用日志，无法在界面上查询。本变更引入操作审计流水，为后续的合规检查提供数据基础。

## What Changes

- 新增 `audit_trail` 表（操作人、动作、目标类型、目标 id、时间）与 `audit-trail` 能力。
- 在账号管理、题库编辑两条写入路径上记录审计条目。
- 新增 `GET /api/audit` 查询接口，支持按操作人、目标类型与时间范围过滤。
- 非目标：不做审计日志的导出与归档；不做操作回滚；不记录读操作。

## Capabilities

- audit-trail（ADDED：审计记录写入、审计流水查询）

## Impact

- 后端：`backend/app/db.py`（新增 audit_trail 表）、`backend/app/routers/accounts.py`、`backend/app/routers/questions.py`
- 前端：`frontend/src/views/admin/AuditPage.vue`
- 兼容性：新增表与新增端点，无破坏性变更
