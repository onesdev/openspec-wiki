# audit-trail 变更增量

## ADDED Requirements

### Requirement: 审计记录写入
账号管理与题库编辑的写操作 SHALL 在业务事务内同步写入审计条目，条目 MUST 包含操作人、动作、目标类型、目标 id 与时间。

#### Scenario: 修改账号角色
- **WHEN** 管理员把某账号的角色从 `student` 改为 `grader`
- **THEN** 业务变更与一条 `update` 审计条目在同一事务内落库

### Requirement: 审计流水查询
管理员 SHALL 能按操作人、目标类型与时间范围查询审计流水，结果 MUST 按时间倒序返回。

#### Scenario: 按目标类型过滤
- **WHEN** 管理员以目标类型 `question` 查询审计流水
- **THEN** 仅返回目标类型为 `question` 的条目，按时间倒序排列
