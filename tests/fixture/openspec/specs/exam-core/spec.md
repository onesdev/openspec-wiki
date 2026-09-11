# exam-core

## Purpose

考试的创建、状态流转与考生可见性。考试是判分与成绩的归属主体。

## Requirements

### Requirement: 考试创建
管理员 SHALL 能创建考试并指定名称、时长、考生人数与题目列表；创建成功的考试 MUST 以 `draft` 状态落库，且不立即对考生可见。

#### Scenario: 创建成功
- **WHEN** 管理员提交合法的名称、时长与题目列表
- **THEN** 考试以 `draft` 状态落库并返回考试 ID

#### Scenario: 名称为空
- **WHEN** 管理员提交的考试名称为空串
- **THEN** 请求被拒，返回 400 与「考试名称不能为空」

### Requirement: 考试状态流转
考试状态 MUST 取值于 `draft` / `published` / `closed`，且只允许 `draft → published → closed` 单向推进。

#### Scenario: 非法状态值
- **WHEN** 管理员提交 `status` 为三个合法值之外的内容
- **THEN** 请求被拒，返回 400 与「考试状态非法」

### Requirement: 考生可见范围
考生 SHALL 只能看到 `published` 与 `closed` 状态的考试；`draft` 考试 MUST NOT 出现在考生列表中。

#### Scenario: 考生查看我的考试
- **WHEN** 考生请求我的考试列表
- **THEN** 仅返回 `published` 与 `closed` 的考试
