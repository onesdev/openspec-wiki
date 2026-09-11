# 考试核心能力提案

## Change ID

exam-core

## Why

平台最初只有题库与账号两块，缺少「考试」这一主体：判分结果无处归属，考生也没有「我能参加哪些考试」的入口。本变更引入考试实体与状态机，把题目、账号、成绩串起来。

## What Changes

- 新增 `exams` 表（名称、时长、状态、创建人）与 `exam-core` 能力。
- 新增 `POST /api/exams`（创建）、`GET /api/exams`（列表）、`POST /api/exams/{id}/status`（状态流转）。
- 考试状态限定 `draft` / `published` / `closed` 三值，单向推进。
- 考生侧新增「我的考试」，仅返回 `published` 与 `closed`。
- 非目标：不引入考试模板；不做考试复制；不做定时自动开考与自动收卷。

## Capabilities

- exam-core（ADDED：考试创建、状态流转、考生可见范围）

## Impact

- 后端：`backend/app/db.py`（新增 exams 表）、`backend/app/routers/exams.py`、`backend/app/routers/student.py`
- 前端：`frontend/src/views/ExamListPage.vue`
- 兼容性：新增表与新增端点，无破坏性变更
