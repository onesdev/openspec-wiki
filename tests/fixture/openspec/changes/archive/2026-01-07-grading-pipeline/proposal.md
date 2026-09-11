# 判分流水线提案

## Change ID

grading-pipeline

## Why

判分此前把用例数写死为 20，导致轻量题目（随堂练习、演示题）被迫凑满用例；同时成绩存储没有记录提交语言，同一道题多语言提交会互相覆盖代码。

## What Changes

- 新增 `grading-pipeline` 能力：判分按 `round(passed / total * 100)` 折算，`total` 取题包实际用例数。
- `submissions` 表补 `lang` 列，唯一键从 `(exam, user, question)` 扩到含 `lang`。
- `saved_codes` 表因唯一键变更需整表重建（建新表 → 拷数 → 改名）。
- 非目标：不引入小数分或加权计分；不做判分结果的实时推送。

## Capabilities

- grading-pipeline（ADDED：判分折算、提交语言）

## Impact

- 后端：`backend/app/db.py`（`submissions.lang` 补列、`saved_codes` 重建）、`backend/app/routers/student.py`
- 兼容性：`saved_codes` 重建在迁移中完成，存量代码不丢
