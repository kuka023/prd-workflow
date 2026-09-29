# AGENTS.md

本文件面向在本需求库中工作的所有 AI agent，包括起草与审稿需求的 agent，以及读取需求进行实现的 coding agent。

**规则的唯一真源是 [constitution.md](constitution.md)。** 本文件只给出阅读顺序与最常用的规则摘要；二者不一致时，以 constitution 为准。各文件属于核心、领域包还是项目适配，见 [FRAMEWORK.md](FRAMEWORK.md)。

---

## 1. 阅读顺序

按「核心 → 已启用领域包 → 项目」的顺序（CN-8）：

1. `constitution.md`：全部规则
2. `00-context/project.md`：本项目启用的领域包与新增的验收层级；启用的领域包见 `domain-packs/<包>/README.md`
3. `00-context/glossary.md`、`personas.md`、`modules.md`：术语、角色与模块
4. 目标需求文件，以及其 `depends_on`、`business_requirements` 中的需求
5. `02-contracts/`：实体、字段、接口、链路 I/O
6. 含效果验收章节的需求另读 `03-quality/`，以及需求引用的验收方案（`03-quality/acceptance/`）

`pilot-history/` 是试点历史材料，不作为任何项目的事实来源。

## 2. 所有 agent 必须遵守

- **不编造。** 素材中没有依据的业务规则、权限、流程、字段、数字，一律不写成事实。未知项写 `[待补充/类别: 问题 — @负责人]`；数字未知写 `[待定]` 或 `[待测]`（CN-20 至 CN-33）。
- 以 `CTX` 为来源时，所依据的上下文条目须已确认（来源不是提案，CN-9、CN-21）。
- 术语与角色 ID 只取自 `00-context/`；字段与接口只取自 `02-contracts/`，不在需求中复制定义（CN-1、CN-2）。领域包只提供候选，登记到项目适配后才可引用。
- 门槛、基线与波动范围只写在验收方案中；需求的 `M-n` 以「方案 ID · 版本 · TH-n」引用（CN-3、CN-57）。
- 引用一律使用编号（`BR-3`、`AC-12`），不写「见第 X 节」（CN-13）。
- 决策层内容只提建议，不代为决定（constitution 第 6 节）。
- 写入文件的内容使用专业、正式的书面口吻（CN-38）。
- 默认按业务目标编写 `spec_kind: business`；有依据时可拆出 `capability`，并关联最终业务验收。两者按实际承诺同时覆盖功能与效果，不沿用互斥的 functional / effect 分类（CN-47、CN-48、CN-52、CN-53）。

## 3. 起草与审稿需求

使用本库的 Skill，不另起流程：

| Skill | 用途 |
|---|---|
| `/prd-context-init` | 从项目已有文档起草或更新项目适配，输出确认清单（CN-9） |
| `/prd-generate <ID>` | 从素材包 `inputs/<ID>/input.md` 生成初稿，**须在新会话中运行**（CN-70） |
| `/prd-review-refine <ID>` | 独立审稿与修订，**须在新会话或子代理中运行** |
| `/prd-lint` | 确定性检查（`scripts/prd_lint.py`） |
| `/prd-distill capture <ID>` | 精修完成后比对初稿与定稿，起草修改原因、类型与归属层 |
| `/prd-distill` | 从精修案例分层提炼规则，并在盲测案例上回归 |

外部工具或 Skill 不得另起一份需求规格、数据契约或指标口径（CN-6）。

## 4. 实现需求（coding agent）

- **只实现 `status: frozen` 的需求**（CN-60）。以达到效果门槛为目的的调优工作，另须所引用的验收方案已冻结（CN-56）。
- 遇到 `[待补充]`、`[待定]`，或遇到需求「实现方须停止并确认的情形」中列出的 `STOP-n`，**停止并提出，不自行补全**（CN-61）。
- 任务拆解与实现计划由实现方负责，任务编号使用 `<需求ID>.Tn`（CN-62）。
- 合并请求的描述须列出「规格未覆盖、由实现方自行决定的事项」，并注明相关编号（CN-63）。
- commit message 以需求 ID 开头（CN-64）。

## 5. 常用命令

```bash
python3 scripts/prd_lint.py                                 # 全库检查（含验收方案）
python3 scripts/prd_lint.py --file <需求文件> --as review    # 预检能否提交评审
python3 scripts/generate_status.py                          # 更新 status.md、open-questions.md 与 decisions.md
```
