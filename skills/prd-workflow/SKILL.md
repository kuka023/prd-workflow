---
name: prd-workflow
description: AI 协作 PRD 工作流。从项目已有文档初始化项目上下文，再按需求从素材生成 PRD 初稿、独立审稿、确定性检查，输出待决策清单；精修后记录案例并提炼规则，持续改进。每条内容标注来源，不编造。用于：初始化需求库、写 PRD、根据会议纪要或素材写需求、审稿、检查能否提交评审或定稿、查看需求状态与待决事项、记录精修案例、提炼规则。命令：/prd-workflow init | new 需求ID | generate | review | lint | status | capture | distill。
license: MIT
allowed-tools: Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/*)
---

# prd-workflow

一套 AI 协作编写 PRD 的工作流：方法与纪律固定，领域与项目事实通过适配层提供。AI 负责把文档写全、写规范，并把需要人决策的问题列清楚；业务事实、范围取舍、权限与门槛由决策方确定。

运行环境需要 Python 3（仅标准库），建议在 Git 仓库中使用。独立生成与审稿依赖子代理；不支持子代理的环境须手动开启新会话。

## 路径约定

- **Skill 目录**（下文写作 `<SKILL>`）：`${CLAUDE_SKILL_DIR}`。该变量未被替换时，即本 `SKILL.md` 所在的目录。
- **项目需求库**：当前工作目录中含 `00-context/project.md` 的目录。尚未初始化时为当前工作目录。
- 以 `core/`、`stages/`、`templates/`、`references/`、`scripts/` 开头的路径均相对 `<SKILL>`；`00-context/`、`01-requirements/`、`inputs/`、`cases/` 等均相对项目需求库。
- 领域包按「项目的 `domain-packs/<包名>/` → `<SKILL>/domain-packs/<包名>/`」的顺序查找。
- 运行脚本时写作 `python3 <SKILL>/scripts/<脚本名>`，在项目需求库目录中执行；`<SKILL>` 路径含空格时加引号。

## 任何阶段开始前

1. 读取 `core/constitution.md`，全部规则以它为准；本文件与各阶段说明中的 `CN-n` 均指该文件。
2. 项目需求库已存在时，核对 `00-context/project.md` 的 `framework_version` 与 `core/constitution.md` 的 `version`；不一致时先告知用户，并说明可按 constitution 变更记录迁移。
3. **Skill 目录只读。** 在项目中工作时不修改 `<SKILL>` 下的任何文件；需要改进核心的，按提炼阶段形成上游提案（CN-72）。
4. 写入文件的内容使用专业、正式的书面口吻（CN-38）；不编造，未知项按 CN-30 标记。
5. 生成或审稿时读取 `references/module-selection.md`，按实际能力特征选择条件模块，判断依据保存在生成报告（CN-58）；重要未知项进入开放问题，不增加逐章审批步骤。

## 命令

| 命令 | 做什么 | 执行说明 |
|---|---|---|
| `/prd-workflow init` | 创建需求库骨架，从项目已有文档起草项目上下文，输出确认清单 | `stages/init.md` |
| `/prd-workflow init --confirm` | 把用户对确认清单的答复写回项目上下文 | `stages/init.md` |
| `/prd-workflow init --update` | 有新文档时增量更新项目上下文 | `stages/init.md` |
| `/prd-workflow new <需求ID>` | **单份需求全流程**：素材包 → 独立生成 → 独立审稿 → 检查 → 待决策清单 | 本文件「全流程」 |
| `/prd-workflow generate <需求ID>` | 只做生成 | `stages/generate.md` |
| `/prd-workflow review <需求ID>` | 只做审稿（可加 `--no-edit`、`--score-only`） | `stages/review.md` |
| `/prd-workflow lint` | 确定性检查（可加 `--file <需求文件> --as review`） | `stages/lint.md` |
| `/prd-workflow status` | 更新并汇总需求状态、开放问题与决策台账 | 本文件「状态」 |
| `/prd-workflow capture <需求ID>` | 精修完成后记录案例：修改原因、修改类型与归属层 | `stages/distill.md` |
| `/prd-workflow distill` | 从案例提炼规则（可加 `--regress` 做盲测回归） | `stages/distill.md` |

用户未给出命令、只描述了意图时，按意图选择命令，并先说明将要执行哪一步。当前目录尚无需求库时，先建议 `init`。执行某一阶段时，完整读取对应的阶段说明并严格按其步骤执行。

## 全流程：`/prd-workflow new <需求ID>`

### 1. 前置检查（主会话）

- 需求库已初始化，且 `00-context/modules.md` 已登记该需求 ID 的前缀；否则先完成 `init`。
- 目标需求文件不存在时，按模块在 `01-requirements/<模块>/` 下创建，只写 frontmatter（`id`、`title`、`module`、`spec_kind`、`batch`、`owner`、`status: draft`、`template_version`）。
- 素材包 `inputs/<需求ID>/input.md` 不存在时，以 `templates/input.md` 为模板创建，请用户提供素材（会议纪要、Demo、客户材料、原型），并登记为 `SRC-n`。**主会话只登记素材和用户确认的事实，不起草需求内容**，以保证生成在独立上下文中进行。
- 需求负责人尚未确认规模（A / B / C）时，按 CN-45 给出建议并请其确认。A 级不写 PRD，到此结束。

### 2. 生成（独立子代理）

启动一个子代理，只传入以下内容，不传入主会话的讨论与推断：

> 你在项目需求库 `<项目目录>` 中执行 prd-workflow 的生成阶段。Skill 目录为 `<SKILL>`。完整阅读 `<SKILL>/stages/generate.md` 并严格执行，需求 ID 为 `<需求ID>`。遇到停止条件（G-STOP-n）或需要用户确认规模时，不要猜测，停止并返回需要向用户提出的问题及你建议的选项。完成后返回：生成报告路径、lint 结果摘要、提案与开放问题数量。

- 子代理返回停止问题时，在主会话中按「一次一问、给选项、标推荐」的方式向用户提问；把答复登记为素材包中的 `SRC-n`（类型「口头确认」），再启动**新的**子代理重新生成。
- 生成完成后，若存在 `cases/<需求ID>/`，将需求文件复制为 `cases/<需求ID>/draft-v0.md`，并在 `case.yaml` 中记录 `draft_generated_in_fresh_session: true`。建议用户在任何修改前提交初稿（CN-70）；是否提交由用户决定。

### 3. 审稿（另一个独立子代理）

启动一个新的子代理：

> 你在项目需求库 `<项目目录>` 中执行 prd-workflow 的审稿阶段。Skill 目录为 `<SKILL>`。完整阅读 `<SKILL>/stages/review.md` 并严格执行，需求 ID 为 `<需求ID>`，模式为默认模式。你没有参与这份需求的起草，只依据文件审稿。完成后返回：P0–P3 问题数、编造与遗漏数、需要人来决策的事项、门禁状态。

### 4. 检查与台账（主会话）

```bash
python3 <SKILL>/scripts/prd_lint.py --file <需求文件> --as review
python3 <SKILL>/scripts/generate_status.py
```

### 5. 汇报

向用户汇报，**决策事项放在最前**：

1. 需要人来决策的事项：`Q-n` 与建议口径，按决策方（业务 / PO / 我方）分组；
2. 门禁状态：距离 `review` 还差什么；
3. 生成与审稿的主要发现：编造、遗漏、P0 / P1；
4. 下一步：人工决策与精修 → 含效果要求时 PO 建立或更新验收方案 → `lint --as review` → 改状态；精修完成后运行 `/prd-workflow capture <需求ID>`。

**不支持子代理的环境**：第 2、3 步分别请用户在新会话中运行 `/prd-workflow generate <需求ID>` 与 `/prd-workflow review <需求ID>`，并说明原因：生成与审稿共享上下文会产生相同的盲区。

## 状态：`/prd-workflow status`

```bash
python3 <SKILL>/scripts/generate_status.py
python3 <SKILL>/scripts/prd_lint.py --errors-only
```

汇总 `status.md`、`decisions.md`：各需求状态与门禁阻断项；按决策方分组的未决问题；验收方案中待定的门槛；项目上下文中待确认的提案。先给结论，再列明细。
