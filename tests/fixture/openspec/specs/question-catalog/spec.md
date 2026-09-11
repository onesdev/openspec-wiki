# question-catalog

## Purpose

题库的浏览、详情与内置资产下载。题目分编程题与 SQL 题两类，两类共享同一份列表与详情结构。

## Requirements

### Requirement: 题库列表
管理员与阅卷人 SHALL 能按创建时间倒序浏览题目列表，列表项 MUST 至少包含 ID、标题与题型。

#### Scenario: 浏览题库
- **WHEN** 阅卷人请求题库列表
- **THEN** 返回按创建时间倒序的题目数组，每项含 id / title / type / created_at

### Requirement: 题目详情与关联题库
题目详情 SHALL 返回题目自身字段，并在题目引用了 SQL 题库时一并返回题库 uid 与展示名。

#### Scenario: 查看引用了题库的题目
- **WHEN** 管理员请求一道 `database_uid` 非空的题目详情
- **THEN** 响应含 `database_uid` 与 `database_name` 两个字段

### Requirement: 内置资产下载
平台 SHALL 提供出题模板包的整包下载，响应 MUST 为 `application/zip` 二进制流而非 JSON。

#### Scenario: 下载模板包
- **WHEN** 管理员请求模板包下载
- **THEN** 返回 `application/zip` 响应，浏览器直接触发下载
