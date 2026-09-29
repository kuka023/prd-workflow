# 维护说明

本仓库是 prd-workflow Skill 的源码仓库（Claude Code 插件 + 插件市场），不是某个项目的需求库。

- Skill 位于 `skills/prd-workflow/`；规则唯一真源是 `skills/prd-workflow/core/constitution.md`。
- 修改规则须提升 constitution 的 `version`，并同步 `scripts/prd_lint.py` 的 `LINT_SPEC_VERSION`、各阶段说明的「适配规范版本」、`templates/requirement-prd.md` 与项目骨架中的版本号（CN-50）；发布时提升 `.claude-plugin/plugin.json` 的 `version`。
- 修改后运行 `python3 -m unittest discover -s tests`，并运行 `claude plugin validate .`。
- 本地试用：`claude --plugin-dir .`，或在项目需求库中以 `PRD_ROOT` 指定项目目录运行脚本。
- 仓库公开：不得提交任何客户材料、项目名称或内部信息；`tests` 中有检查。本地的试点材料放在已排除的目录中，不纳入版本控制。
- 写入文件的内容使用专业、正式的书面口吻。
