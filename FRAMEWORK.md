---
title: 框架分层与资源边界
framework_version: "1.2"
updated: 2026-09-29
---

# 框架分层与资源边界

本文件说明本库每个文件属于哪一层（CN-7），以及哪些文件构成可复用的通用核心。安装与分发方式暂不确定；在确定之前，以本文件界定资源边界，不让安装机制阻塞案例积累。

---

## 1. 三层与需求素材

| 层 | 回答的问题 | 变化频率 | 维护方式 |
|---|---|---|---|
| **核心** | PRD 怎么想、怎么写、怎么检查、怎么迭代 | 按规范版本升级 | 需求负责人批准，AI 起草 |
| **领域包** | 某类产品通常有哪些术语、指标、红线、契约与输入形态 | 很少变化 | 从同类项目的案例中提炼 |
| **项目适配** | 本项目的术语、角色、模块、契约、质量口径与验收方案 | 随项目演进 | AI 从已有文档整理，需求负责人确认 |
| 需求素材 | 这一份需求要解决什么、依据是什么 | 每份需求不同 | 需求负责人提供 |

决定单份 PRD 质量的主要是需求素材；项目适配保证术语、角色、契约使用正确；核心保证方法与纪律一致。

---

## 2. 文件归属

### 2.1 核心（可复用，所有项目共用）

| 路径 | 内容 |
|---|---|
| `constitution.md` | 规则唯一真源 |
| `rubric.md` | 质量评分与过程指标 |
| `FRAMEWORK.md` | 本文件 |
| `AGENTS.md`、`CLAUDE.md` | AI agent 入口 |
| `01-requirements/_TEMPLATE-module-prd.md` | 需求模板（含写作说明） |
| `01-requirements/_GUIDE.md` | 需求边界与模板裁剪 |
| `03-quality/acceptance/_TEMPLATE-acceptance-plan.md` | 验收方案模板 |
| `04-decisions/_TEMPLATE-adr.md` | 决策记录模板 |
| `domain-packs/_TEMPLATE/` | 领域包模板 |
| `inputs/_TEMPLATE/` | 素材包、审稿结果模板 |
| `cases/README.md`、`cases/_TEMPLATE/` | 精修案例说明与模板 |
| `.claude/skills/` | 项目适配初始化、生成、审稿、lint、规则提炼 Skill；核心规则在 `.claude/skills/<Skill>/references/learned-rules.md` |
| `scripts/` | `prd_lint.py`、`generate_status.py`、`prdlib.py`、`test_prd_lint.py`、`commit-msg` |

### 2.2 领域包（按产品类型启用）

领域包的**格式**属于核心，见 `domain-packs/_TEMPLATE/`；具体领域包的**内容**不属于核心，按产品类型建设与分发，放在 `domain-packs/<包名>/`。

项目在 `00-context/project.md` 的 `domain_packs` 中声明启用；不启用任何领域包也是正常情况。候选领域包须在第二个同类项目中验证后才转为正式（CN-72）。

### 2.3 项目适配（每个项目一份）

以下文件在核心目录中以骨架形式提供，由项目填写：

| 路径 | 内容 |
|---|---|
| `00-context/project.md` | 项目声明：规范版本、启用的领域包、新增验收层级；项目适配待确认事项 |
| `00-context/sources.md` | 项目素材登记（`PS-n`），项目适配条目的来源（CN-9） |
| `00-context/modules.md`、`glossary.md`、`personas.md` | 模块、术语、角色与权限 |
| `00-context/learned-rules.md` | 项目规则（CN-72） |
| `02-contracts/` | 实体、字段、接口、链路 I/O |
| `03-quality/metrics.md`、`eval-sets.md`、`nfr.md` | 指标口径与红线、评测集登记、全局非功能需求 |
| `03-quality/acceptance/AP-nnn-*.md` | 验收方案（CN-57） |
| `04-decisions/ADR-nnn-*.md` | 跨需求决策 |
| `01-requirements/<模块>/`、`inputs/<需求ID>/`、`cases/<需求ID>/` | 需求、素材、精修案例 |
| `inputs/_project/` | 项目级素材原件与初始化报告 |
| `status.md`、`open-questions.md`、`decisions.md` | 脚本生成 |

### 2.4 不属于任何一层

| 路径 | 说明 |
|---|---|
| `pilot-history/` | 试点历史材料，只读，不参与检查，不随核心发布 |

---

## 3. 新项目怎样开始

1. 复制 2.1 所列的核心文件、2.2 中可能用到的领域包，以及 2.3 所列的骨架文件（复制方式暂为手工）；
2. 运行 `/prd-context-init`，提供项目已有文档。Skill 登记素材、起草项目适配、建议启用的领域包与候选需求划分，输出按决策方分组的确认清单；
3. 需求负责人确认我方可定的事项，业务方确认口径与权限；运行 `/prd-context-init --confirm` 回写；
4. 按需求准备素材包，开始生成。

项目适配不必一次完整：缺项不阻止生成，但对应内容会以待补充标记。后续有新文档时运行 `/prd-context-init --update`。

---

## 4. 升级

核心规范版本变化时，`prd_lint.py` 对 `template_version` 落后的需求给出提示（CN-51）。升级按 `constitution.md` 变更记录逐项迁移，不为消除提示而只修改版本号。自动升级机制暂不建设。

---

## 5. 迭代

```
每份需求：生成 Skill 在独立会话中生成初稿并原样提交（CN-70）→ 人工修改
       → 规则提炼 Skill「记录」模式：比对差异，起草修改原因、修改类型与归属层 → 需求负责人确认
每积累 3–5 个案例：「提炼」模式提出规则变更 → 需求负责人批准 → 在盲测案例上回归（CN-73）
```

| 修改类型 | 去向 |
|---|---|
| 决策类 | 开放问题结论，进入项目适配或 ADR（CN-71） |
| 非决策类 | 按 CN-72 进入核心、领域包、项目规则或 lint；只出现一次的留在案例中 |
