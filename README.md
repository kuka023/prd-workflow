# prd-workflow · AI 协作 PRD 工作流

> An agent skill for writing PRDs with AI: initialize project context from existing documents, generate drafts from source materials, review them independently, run deterministic checks, and improve from refined cases. Every statement carries a source; nothing is fabricated. Documentation is in Chinese.

一个用于 AI 协作编写 PRD 的 Agent Skill。需求负责人提供项目上下文与需求素材，AI 按固定的方法生成 PRD 初稿、独立审稿、自动检查，把需要人决策的问题整理成清单；需求负责人的时间主要花在决策上，而不是补结构、改格式、纠正编造。

**状态：0.2.0 预览版（规范 1.4）。** 方法、规则与检查脚本已完整，正在真实项目中试点验证；规则可能随试点结果调整。

---

## 它解决什么问题

让 AI 直接写 PRD，常见的问题是：文档看起来完整，但有些业务规则、权限、数字是模型补出来的；评审者因为文档完整而放松，开发把编造的内容当成事实实现。

本工作流的做法：

- **每条内容标注来源**：素材（`SRC-n`）、项目上下文（`CTX`）、已决问题（`Q-n`），或明确标为「提案」待决策。没有依据的写成待补充，并给出建议口径。`SRC-n` 同时显示业务可读名称并链接到来源卡片，业务评审者可以核对原文、材料性质及证据边界。
- **决策层与表达层分开**：结构、措辞、格式由 AI 直接写；问题定义、范围、规则、权限、门槛只能由 AI 提建议，由决策方确定。
- **生成与审稿相互独立**：初稿与审稿分别在独立的子代理中进行，避免共享同样的盲区。
- **能由脚本判定的由脚本判定**：来源、编号、覆盖率、门禁等由 `prd_lint.py` 检查，不依赖模型自觉。
- **越用越准**：精修后记录「初稿哪里不对、为什么这样改」，区分决策类与非决策类修改，分层提炼规则，并在盲测案例上回归。

## 三层结构

| 层 | 内容 | 在哪里 |
|---|---|---|
| **核心** | 方法、规则、模板、阶段说明、检查脚本 | 本 Skill |
| **领域包** | 某类产品共用的术语、指标、红线、输入形态等候选清单 | 本 Skill 自带模板；具体领域包放在项目中 |
| **项目适配** | 本项目的术语、角色、模块、契约、质量口径、验收方案 | 你的项目需求库 |

项目需求库只存放项目自己的内容，不复制核心；更新 Skill 即更新核心。开发人员与 coding agent 读取项目中的 `AGENTS.md` 即可按需求实现，**无须安装本 Skill**。

---

## 安装

### Claude Code（推荐）

```text
/plugin marketplace add kuka023/prd-workflow
/plugin install prd-workflow@prd-workflow
```

安装后以 `/prd-workflow:prd-workflow` 调用，也可以直接用自然语言描述要做的事（如「用 prd-workflow 初始化需求库」）。更新：`/plugin marketplace update prd-workflow`。

### 作为个人 Skill（适用于 Claude Code 及其他支持 Agent Skills 标准的工具）

```bash
git clone https://github.com/kuka023/prd-workflow.git
cp -R prd-workflow/skills/prd-workflow ~/.claude/skills/
```

安装后以 `/prd-workflow` 调用。其他工具请将 `skills/prd-workflow/` 放到该工具读取 Skill 的目录。不支持子代理的环境，生成与审稿须手动在新会话中进行。

**依赖**：Python 3（仅标准库）；建议在 Git 仓库中使用。

---

## 使用

### 1. 初始化项目

在准备存放需求库的目录中：

```text
/prd-workflow init
```

提供项目已有的文档（既有 PRD、用户旅程、系统说明、角色清单、数据字典、会议纪要等）。Skill 会创建需求库骨架，登记素材，起草术语、角色与权限、模块、核心实体等项目上下文，建议需求如何划分，并输出**按决策方分组的确认清单**：模块划分等我方可定的事项给出草拟结论，术语口径、权限、红线交业务方确认。确认后运行 `/prd-workflow init --confirm` 回写。

### 2. 写一份需求

```text
/prd-workflow new ABC-001
```

依次完成：准备素材包 → 在独立子代理中生成初稿 → 在另一个独立子代理中审稿与修订 → 自动检查 → 汇报。汇报把**需要你决策的事项放在最前**，附建议口径，并说明距离提交评审还差什么。

### 3. 决策、精修与定稿

处理开放问题与提案，与业务方确认；含效果要求的需求，由 PO 在验收方案中确定门槛（需求只引用「方案 · 版本 · 门槛条目」，不写数值）。然后检查能否进入下一状态：

```text
/prd-workflow lint --file 01-requirements/abc/ABC-001-xxx.md --as review
```

### 4. 记录与改进

```text
/prd-workflow capture ABC-001   # 精修完成后：AI 比对初稿与定稿，起草修改原因、类型与归属层，你来确认
/prd-workflow distill           # 每积累 3–5 个案例：提出规则变更，批准后在盲测案例上回归
/prd-workflow status            # 需求状态、按决策方汇总的未决问题、待定门槛
```

### 命令一览

| 命令 | 作用 |
|---|---|
| `init` / `init --confirm` / `init --update` | 初始化需求库与项目上下文 / 回写确认 / 增量更新 |
| `new <需求ID>` | 单份需求全流程 |
| `generate <需求ID>` / `review <需求ID>` | 单独生成 / 单独审稿 |
| `lint` | 确定性检查 |
| `status` | 状态与决策台账 |
| `capture <需求ID>` / `distill` | 记录案例 / 提炼规则与回归 |

---

## 项目需求库的结构

```
├── AGENTS.md / CLAUDE.md   面向开发与 coding agent 的说明
├── status.md               需求状态（生成）
├── decisions.md            按决策方汇总的未决事项（生成）
├── 00-context/             项目声明、素材登记、模块、术语、角色与权限、项目规则
├── 01-requirements/        需求文件
├── 02-contracts/           实体、字段、接口
├── 03-quality/             指标口径、评测集、非功能需求；acceptance/ 下为带版本的验收方案
├── 04-decisions/           跨需求决策记录
├── inputs/                 需求素材包（原件放 raw/，默认不提交）
└── cases/                  精修案例
```

## 本仓库的结构

```
├── .claude-plugin/          插件与插件市场清单
├── skills/prd-workflow/
│   ├── SKILL.md             入口与全流程编排
│   ├── core/                规则（constitution）、评分标准、分层说明、划分指南、案例说明
│   ├── stages/              各阶段说明：init / generate / review / lint / distill
│   ├── references/          审稿清单、已提炼的核心规则
│   ├── templates/           需求、素材包、验收方案、ADR、案例模板；project/ 为项目骨架
│   ├── domain-packs/        领域包模板
│   └── scripts/             prd_lint.py、generate_status.py、commit-msg 钩子
└── tests/                   回归测试
```

规则全文：[skills/prd-workflow/core/constitution.md](skills/prd-workflow/core/constitution.md)。

---

## 参与改进

核心规则只在本仓库中修改。在你的项目中运行 `/prd-workflow distill` 时，可能成为核心规则或检查项的经验会整理为上游提案（`cases/upstream-proposals-<日期>.md`），欢迎以 issue 或 pull request 提交。**提交前请去除客户材料与项目敏感信息。**

核心规则的准入条件：在至少两个不同项目的案例中出现，不依赖特定领域或客户背景，能写出触发条件、正例、反例与停止条件；规则变化须在盲测案例上回归，且改善超出同一版本重复运行的波动范围。

修改脚本后运行测试：

```bash
python3 -m unittest discover -s tests
```

## 版本与回滚

- Skill 发布版本使用 SemVer，写在 `.claude-plugin/plugin.json`；规范版本写在 `core/constitution.md`。两者映射、迁移影响和回滚目标记录在 [CHANGELOG.md](CHANGELOG.md)。
- 每次对外发布创建不可变 tag `v<Skill 发布版本>` 并生成同名 GitHub Release；不移动或覆盖已经发布的 tag。
- 需要固定或回滚时，从对应 tag 安装。例如 `git clone --branch v0.2.0 --depth 1 https://github.com/kuka023/prd-workflow.git`。仓库维护者撤销已合并变更时使用 `git revert` 并发布新版本，不改写 `main` 历史。
- 项目通过 `framework_version` 和需求的 `template_version` 固定所依据的规范。回滚 Skill 不会自动改写项目需求；项目应按目标版本的迁移说明处理后再修改版本号。

## 许可

[MIT](LICENSE)
