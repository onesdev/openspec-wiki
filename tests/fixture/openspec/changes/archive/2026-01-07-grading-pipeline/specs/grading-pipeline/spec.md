# grading-pipeline 变更增量

## ADDED Requirements

### Requirement: 判分折算
判分 SHALL 按 `round(passed / total * 100)` 折算百分制得分；`total` MUST 取题包实际用例数而非固定值。

#### Scenario: 用例数不足默认值
- **WHEN** 题目题包仅含 3 条用例且全部通过
- **THEN** 得分为 100

#### Scenario: 部分通过
- **WHEN** 3 条用例中通过 2 条
- **THEN** 得分为 67

### Requirement: 提交语言
每次提交 MUST 记录所用语言，且同一道题允许考生以不同语言重复提交并各自保存代码。

#### Scenario: 同一题两种语言提交
- **WHEN** 考生先以 python 提交、再以 cpp 提交同一道题
- **THEN** 两份代码各自独立保存，互不覆盖
