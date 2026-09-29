---
title: 框架分层与资源边界
framework_version: "1.3"
updated: 2026-09-29
---

# 框架分层与资源边界

本文件说明每个文件属于哪一层（CN-7）、存放在哪里。**核心就是 prd-workflow Skill 本身**；每个项目有自己的需求库目录，只存放项目适配、需求、素材与案例。

---

## 1. 三层与需求素材

| 层 | 回答的问题 | 存放位置 | 变化方式 |
|---|---|---|---|
| **核心** | PRD 怎么想、怎么写、怎么检查、怎么迭代 | Skill 目录 | 在 Skill 上游仓库修改并发布；项目通过更新 Skill 获得 |
| **领域包** | 某类产品通常有哪些术语、指标、红线、契约与输入形态 | 项目的 `domain-packs/<包名>/`，或 Skill 自带的 `domain-packs/` | 从同类项目的案例中提炼 |
| **项目适配** | 本项目的术语、角色、模块、契约、质量口径与验收方案 | 项目需求库 | 初始化阶段从已有文档起草，需求负责人确认 |
| 需求素材 | 这一份需求要解决什么、依据是什么 | 项目的 `inputs/<需求ID>/` | 需求负责人提供 |

决定单份 PRD 质量的主要是需求素材；项目适配保证术语、角色、契约使用正确；核心保证方法与纪律一致。

---

## 2. Skill 目录（核心）

| 路径 | 内容 |
|---|---|
| `SKILL.md` | 入口：各阶段的调用方式与全流程编排 |
| `core/constitution.md` | 规则唯一真源 |
| `core/rubric.md` | 质量评分与过程指标 |
| `core/framework.md` | 本文件 |
| `core/guide.md` | 需求边界与模板裁剪 |
| `core/cases-guide.md` | 精修案例与规则提炼的说明 |
| `stages/` | 各阶段的执行说明：初始化、生成、审稿、检查、提炼 |
| `references/` | 审稿清单；核心规则（`learned-rules-generate.md`、`learned-rules-review.md`） |
| `templates/requirement-prd.md` | 需求模板（含写作说明） |
| `templates/acceptance-plan.md`、`templates/adr.md` | 验收方案、决策记录模板 |
| `templates/input.md`、`templates/review-findings.yaml` | 素材包、审稿结果模板 |
| `templates/case.yaml`、`templates/lessons.yaml` | 精修案例模板 |
| `templates/project/` | 新项目需求库的骨架，初始化时复制到项目 |
| `domain-packs/_TEMPLATE/` | 领域包模板（领域包的格式属于核心） |
| `scripts/` | `prd_lint.py`、`generate_status.py`、`prdlib.py`、`commit-msg` |

Skill 目录中的文件**不在项目中修改**。核心规则的变化通过上游仓库的提案与发布进行（CN-72、CN-73）。

---

## 3. 项目需求库（项目适配、需求、素材、案例）

初始化阶段以 `templates/project/` 为骨架创建：

| 路径 | 内容 |
|---|---|
| `AGENTS.md`、`CLAUDE.md` | 面向开发与 coding agent 的说明：实现方须遵守的规则（CN-60 至 CN-65），无须安装 Skill 即可读取 |
| `00-context/project.md` | 项目声明：规范版本、启用的领域包、新增验收层级；项目适配待确认事项 |
| `00-context/sources.md` | 项目素材登记（`PS-n`），项目适配条目的来源（CN-9） |
| `00-context/modules.md`、`glossary.md`、`personas.md` | 模块、术语、角色与权限 |
| `00-context/learned-rules.md` | 项目规则（CN-72） |
| `02-contracts/` | 实体、字段、接口、链路 I/O |
| `03-quality/metrics.md`、`eval-sets.md`、`nfr.md` | 指标口径与红线、评测集登记、全局非功能需求 |
| `03-quality/acceptance/AP-nnn-*.md` | 验收方案（CN-57） |
| `04-decisions/ADR-nnn-*.md` | 跨需求决策 |
| `01-requirements/<模块>/` | 需求文件 |
| `inputs/<需求ID>/`、`inputs/_project/` | 需求素材包与生成、审稿报告；项目级素材与初始化报告 |
| `cases/<需求ID>/` | 精修案例 |
| `domain-packs/<包名>/` | 项目自有或私有的领域包（可选） |
| `status.md`、`open-questions.md`、`decisions.md` | 脚本生成的台账 |

---

## 4. 新项目怎样开始

1. 安装 prd-workflow Skill（见 Skill 仓库的 README）；
2. 在准备存放需求库的目录中运行 `/prd-workflow init`，提供项目已有文档。初始化阶段创建需求库骨架、登记素材、起草项目适配，建议启用的领域包与候选需求划分，输出按决策方分组的确认清单；
3. 需求负责人确认我方可定的事项，业务方确认口径与权限；运行 `/prd-workflow init --confirm` 回写；
4. 按需求准备素材包，运行 `/prd-workflow new <需求ID>` 走完单份需求的流程。

项目适配不必一次完整：缺项不阻止生成，但对应内容会以待补充标记。后续有新文档时运行 `/prd-workflow init --update`。

---

## 5. 升级

Skill 更新后，规范版本可能变化。`prd_lint.py` 对 `framework_version` 与当前规范版本不一致的项目、`template_version` 落后的需求给出提示（CN-51）。项目按 `core/constitution.md` 变更记录逐项迁移，不为消除提示而只修改版本号。需要固定版本的项目，固定所安装的 Skill 版本。

---

## 6. 迭代

```
每份需求：生成阶段在独立上下文中生成初稿并原样提交（CN-70）→ 审稿 → 人工精修
       → capture：比对差异，起草修改原因、修改类型与归属层 → 需求负责人确认
每积累 3–5 个案例：distill 提出规则变更 → 需求负责人批准 → 在盲测案例上回归（CN-73）
```

| 修改类型 | 去向 |
|---|---|
| 决策类 | 开放问题结论，进入项目适配或 ADR（CN-71） |
| 非决策类 | 按 CN-72 进入 lint、核心规则提案、领域包或项目规则；只出现一次的留在案例中 |

核心规则与 lint 检查项的变化以提案形式提交到 Skill 上游仓库（issue 或 pull request），经维护者批准并在盲测案例上回归后发布。
