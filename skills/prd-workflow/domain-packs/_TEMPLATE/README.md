---
title: 领域包名称
status: candidate               # candidate：候选，尚未经两个以上项目验证 | stable：已在两个以上同类项目中验证
framework_version: "1.4"
updated: 2026-09-29
---

# 领域包模板

领域包存放**某一类产品**共用的术语、指标、红线、契约骨架与候选清单（CN-7）。复制本目录为 `domain-packs/<包名>/` 后填写；项目在 `00-context/project.md` 的 `domain_packs` 中声明启用。

领域包只提供候选与提示，**不作为事实来源**：其中的条目经初始化阶段写入项目适配时来源为 `提案`，经项目确认后才可被需求引用（CN-9）。

## 1. 包含什么

| 文件 | 内容 | 项目如何使用 |
|---|---|---|
| `glossary-seed.md` | 该类产品的术语初始条目 | 选取适用条目写入项目的 `00-context/glossary.md` |
| `metrics-seed.md` | 候选指标与候选红线，**不含门槛** | 选取适用条目写入项目的 `03-quality/metrics.md` |
| `contracts-skeleton.md` | 该类产品常见的契约骨架与须贯穿传递的元数据 | 作为项目 `02-contracts/` 的起点 |
| `input-forms.md` | 效果验收中「必须处理的输入形态」候选清单 | 生成与审稿时参考 |
| `boundary-examples.md` | 该类产品的业务 PRD 与能力规格边界示例 | 划分需求时参考 |
| `learned-rules.md` | 从该类产品精修案例中提炼的领域规则 | 生成与审稿 Skill 读取 |

不适用的文件可以删除；README 中同步删除对应行。

## 2. 启用方式

```yaml
# 00-context/project.md
domain_packs: [<包名>]
verification_levels: []         # 本包建议新增的验收层级（如有）
```

## 3. 准入与升级

| 去向 | 条件 |
|---|---|
| 进入本包 | 在至少两份同类需求中重复出现，且不依赖具体客户或业务背景（CN-72） |
| 从候选转为正式 | 在第二个同类项目中被验证有效 |
| 从本包进入核心 | 在其他类型的项目中同样成立 |
