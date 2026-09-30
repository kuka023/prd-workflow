"""选章报告的门禁回归：验证声明与条目一致性，不代替模型的选章评测。"""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from test_prd_lint import SKILL, prd_lint
from prdlib import parse_tables


class ModuleSelectionTests(unittest.TestCase):
    def check(self, changes=None, effect=False, rank=1, missing=None):
        catalog = (SKILL / "references/module-selection.md").read_text(encoding="utf-8")
        keys = [c[0] for t in parse_tables(catalog.splitlines())
                if t.col("触发特征") is not None for _, c in t.rows]
        rows = {key: ["不适用", "本场景已确认的责任边界不包含此能力", "—", "—", "—"] for key in keys}
        rows.update(changes or {})
        for key in missing or []:
            rows.pop(key)
        header = "| 模块 ID | 判定 | 依据或原因 | 正文条目 | 验收条目 | 待确认问题 |\n|---|---|---|---|---|---|\n"
        report = header + "\n".join("| " + " | ".join([k, *v]) + " |" for k, v in rows.items())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "inputs" / "ABC-001" / "generation-report.md"
            target.parent.mkdir(parents=True)
            target.write_text(report, encoding="utf-8")
            lint = prd_lint.Linter(None)
            with mock.patch.object(prd_lint, "ROOT", root):
                lint._check_module_selection("prd.md", "ABC-001", {"ABC-001.1", "BR-1", "AC-1", "M-1", "Q-1"},
                                             set(), effect, rank)
        return {(f.code, f.level) for f in lint.findings}

    def applicable(self, reason):
        return ["适用", reason, "ABC-001.1", "AC-1", "—"]

    def test_deterministic_form_without_effect_chapter(self):
        self.assertEqual(self.check({key: self.applicable("固定表单及保存结果，性能遵循已有约束")
                                     for key in ("INPUT", "OUTPUT", "BUDGET")}), set())

    def test_knowledge_flow_with_unknown_multiturn_support(self):
        rows = {key: self.applicable("素材要求导入、权限引用、更新撤回与生成回答")
                for key in ("INPUT", "META", "TASK", "OUTPUT", "LIFE", "EFFECT", "OPS", "BUDGET")}
        rows["MEMORY"] = ["待确认", "未说明是否多轮会话，须确定责任边界", "—", "—", "Q-1"]
        self.assertEqual(self.check(rows, effect=True), set())
        self.assertIn(("MS04", "error"), self.check(rows, effect=True, rank=2))

    def test_agent_action_is_applicable_even_when_rules_unknown(self):
        rows = {key: self.applicable("助手执行操作并保存会话状态") for key in ("TASK", "OUTPUT", "MEMORY", "EFFECT")}
        rows["ACTION"] = ["适用", "已有执行能力，授权与失败规则未知", "—", "—", "Q-1"]
        self.assertEqual(self.check(rows, effect=True), set())

    def test_missing_modules_and_invalid_state_are_rejected(self):
        self.assertIn(("MS01", "error"), self.check(missing=["ACTION"]))
        self.assertIn(("MS01", "error"), self.check({"ACTION": ["忽略", "原因", "—", "—", "—"]}))

    def test_missing_evidence_and_nonexistent_references_are_rejected(self):
        self.assertIn(("MS01", "error"), self.check({"INPUT": ["不适用", "", "—", "—", "—"]}))
        self.assertIn(("MS02", "error"), self.check({"INPUT": ["适用", "文档处理", "BR-999", "AC-1", "—"]}))
        self.assertIn(("MS02", "error"), self.check({"ACTION": ["待确认", "可能执行", "—", "—", "Q-99"]}))

    def test_effect_declaration_cannot_hide_missing_chapter(self):
        self.assertIn(("MS03", "error"), self.check({"EFFECT": self.applicable("概率性回答")}, effect=False))
        self.assertIn(("MS03", "error"), self.check(effect=True))

    def test_report_failures_warn_in_draft_and_block_review(self):
        row = {"INPUT": ["适用", "有输入形态要求", "—", "—", "—"]}
        self.assertEqual(self.check(row, rank=0), {("MS02", "warn")})
        self.assertEqual(self.check(row, rank=1), {("MS02", "error")})


if __name__ == "__main__":
    unittest.main()
