# AGENTS.md

本文件面向在本需求库中工作的开发人员与 AI agent，尤其是按需求进行实现的 coding agent。

本需求库由 [prd-workflow](https://github.com/kuka023/prd-workflow) 维护：需求的起草、审稿与检查规则由该 Skill 提供，规则全文见其 [constitution](https://github.com/kuka023/prd-workflow/blob/main/skills/prd-workflow/core/constitution.md)（文中 `CN-n` 均指该文件）。**实现需求不需要安装该 Skill**，遵守本文件即可。

---

## 1. 目录

| 路径 | 内容 |
|---|---|
| `status.md` | 全部需求的状态（脚本生成）；从这里开始 |
| `01-requirements/<模块>/<需求ID>-*.md` | 需求文件 |
| `00-context/` | 模块、术语、角色与权限 |
| `02-contracts/` | 实体、字段、接口、链路 I/O |
| `03-quality/` | 指标口径、评测集、全局非功能需求；`acceptance/` 下为带版本的验收方案 |
| `04-decisions/` | 跨需求决策记录（ADR） |
| `decisions.md`、`open-questions.md` | 未决事项台账（脚本生成） |
| `inputs/`、`cases/` | 需求素材与精修案例，供需求起草使用，实现时无须阅读 |

## 2. 实现需求时必须遵守

- **只实现 `status: frozen` 的需求**（CN-60）。以达到效果门槛为目的的调优工作（模型、Prompt、参数、判定方法），另须所引用的验收方案已冻结（CN-56）。
- 遇到 `[待补充]`、`[待定]`、`[待测]`，或遇到需求「实现方须停止并确认的情形」中列出的 `STOP-n`，**停止并提出，不自行补全**（CN-61）。
- 术语与角色只取自 `00-context/`；字段与接口只取自 `02-contracts/`。需求中的 `CTX` 表示依据来自这些文件。
- 需求中的门槛以「方案 ID · 版本 · TH-n」引用 `03-quality/acceptance/` 中的验收方案，以所引版本为准。
- 任务拆解与实现计划由实现方负责，任务编号使用 `<需求ID>.Tn`（CN-62）。
- 合并请求的描述须列出「规格未覆盖、由实现方自行决定的事项」，并注明相关编号（CN-63）。
- commit message 以需求 ID 开头，如 `ABC-001: 增加审批单金额校验`（CN-64）。

## 3. 阅读一份需求

1. frontmatter：`status`、`depends_on`（前置需求）、`business_requirements`（能力规格的最终业务验收归属）。
2. 第 7 至 12 章是直接执行的部分：业务规则（`BR-n`、`DR-n`）、功能条目（`<需求ID>.n`）、异常（`EX-n`）、验收（`AC-n`）、效果验收（`RL-n`、`M-n`、`BC-n`）。每个 `AC-n` 的「验证层级」说明在哪一层测试。
3. 「本版变更」说明相对上一版不要再按什么做（CN-65）。
4. 条目来源：`SRC-n` 为需求素材，`CTX` 为项目上下文，`Q-n` 为已决问题。`frozen` 状态下不存在来源为「提案」的条目。

## 4. 起草与修改需求

需求的起草、审稿与检查使用 prd-workflow Skill（`/prd-workflow`），不另起流程，也不另建需求规格、数据契约或指标口径（CN-6）。
