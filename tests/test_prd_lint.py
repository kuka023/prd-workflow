"""prd-workflow 的回归测试：检查脚本、项目骨架与 Skill 结构。

运行：python3 -m unittest discover -s tests
测试在项目骨架（skills/prd-workflow/templates/project/）的临时副本中进行。
"""

import atexit
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
SKILL = REPO / "skills" / "prd-workflow"
_PROJECT = Path(tempfile.mkdtemp(prefix="prdwf-test-"))
atexit.register(shutil.rmtree, _PROJECT, True)
shutil.copytree(SKILL / "templates" / "project", _PROJECT, dirs_exist_ok=True)
os.environ["PRD_ROOT"] = str(_PROJECT)
sys.path.insert(0, str(SKILL / "scripts"))

import prd_lint  # noqa: E402
from prd_lint import Linter, check_context, check_dependencies, check_plans, load_plans
from prdlib import MODULE_PREFIX, REQ_ID_PATTERN, ROOT, mask_lines, parse_tables, split_frontmatter


class SpecBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.lint = Linter("review")
        self.path = "01-requirements/agent/AGT-003-test.md"
        self.cap = {"id": "AGT-003", "status": "draft", "spec_kind": "capability",
                    "business_requirements": ["QA-001"], "blocks": ["QA-001"], "depends_on": []}
        self.biz = {"id": "QA-001", "status": "draft", "spec_kind": "business",
                    "business_requirements": [], "depends_on": ["AGT-003"], "blocks": []}
        self.reqs = {
            "AGT-003": {"fm": self.cap, "path": ROOT / self.path, "dupes": []},
            "QA-001": {"fm": self.biz, "path": ROOT / "01-requirements/qa/QA-001-test.md", "dupes": []},
        }

    def codes(self):
        return [f.code for f in self.lint.findings]

    def test_acceptance_link_is_not_a_dependency_cycle(self):
        self.lint._check_spec_links(self.path, self.cap, self.reqs, 1)
        self.lint._check_spec_links(self.path, self.biz, self.reqs, 1)
        check_dependencies(self.lint, self.reqs)
        self.assertEqual(self.codes(), [])

    def test_real_dependency_cycle_is_still_rejected(self):
        self.cap["depends_on"] = ["QA-001"]
        self.biz["blocks"] = ["AGT-003"]
        check_dependencies(self.lint, self.reqs)
        self.assertIn("DP03", self.codes())

    def test_missing_acceptance_link_warns_in_draft_and_blocks_review(self):
        self.cap["business_requirements"] = []
        for rank, level in ((0, "warn"), (1, "error")):
            with self.subTest(rank=rank):
                self.lint.findings.clear()
                self.lint._check_spec_links(self.path, self.cap, self.reqs, rank)
                self.assertEqual([(f.code, f.level) for f in self.lint.findings], [("SK02", level)])

    def test_invalid_acceptance_targets_are_rejected(self):
        for refs in (["QA-999"], ["AGT-003"], "QA-001", [None]):
            with self.subTest(refs=refs):
                self.lint.findings.clear()
                self.cap["business_requirements"] = refs
                self.lint._check_spec_links(self.path, self.cap, self.reqs, 1)
                self.assertIn("SK02", self.codes())
        self.cap["business_requirements"] = ["QA-001"]
        for change in ({"spec_kind": "capability"}, {"status": "deprecated"}, {"spec_kind": ""}):
            with self.subTest(change=change):
                self.lint.findings.clear()
                self.reqs["QA-001"]["fm"] = {**self.biz, **change}
                self.lint._check_spec_links(self.path, self.cap, self.reqs, 1)
                self.assertIn("SK02", self.codes())

    def test_legacy_type_does_not_infer_spec_kind(self):
        for kind in ("functional", "effect"):
            with self.subTest(kind=kind):
                self.lint.findings.clear()
                self.lint._check_spec_links(self.path, {"type": kind}, self.reqs, 1)
                self.assertEqual(self.codes(), ["SK01"])

    def test_inline_frontmatter_lists_remain_compatible(self):
        fm, _ = split_frontmatter('---\nspec_kind: capability\nbusiness_requirements: [QA-001] # 归属\n---\n')
        self.lint._check_spec_links(self.path, fm, self.reqs, 1)
        self.assertEqual(self.codes(), [])

    def test_ownership_requires_each_target_owner_and_acceptance_reference(self):
        for owner, ac, expected in (("@PO", "QA-001：AC-1", []), ("", "QA-001：AC-1", ["SK03"]),
                                    ("@PO", "", ["SK03"])):
            with self.subTest(owner=owner, ac=ac):
                self.lint.findings.clear()
                tables = parse_tables([
                    "| 业务 PRD ID | 验收负责人 | 业务验收条目引用 |",
                    "|---|---|---|", f"| QA-001 | {owner} | {ac} |",
                ])
                self.lint._check_acceptance_ownership(self.path, self.cap, tables, 1)
                self.assertEqual(self.codes(), expected)

    def test_explicit_cross_document_reference_is_not_a_local_orphan(self):
        for ref in ("QA-001 AC-1", "QA-001：AC-1", "QA-001 的 AC-1"):
            with self.subTest(ref=ref):
                self.lint.findings.clear()
                self.lint._check_references(self.path, [ref], 1, {}, "AGT-003", self.reqs, 1)
                self.assertNotIn("RF01", self.codes())
        self.lint._check_references(self.path, ["AGT-003：AC-99"], 1, {}, "AGT-003", self.reqs, 1)
        self.assertIn("RF01", self.codes())

    def test_e2e_requires_complete_gwt_and_uses_column_names(self):
        for then, expected in (("保留来源引用", []), ("", ["CV04"])):
            with self.subTest(then=then):
                self.lint.findings.clear()
                tables = parse_tables(mask_lines([
                    "### 11.1 端到端验收",
                    "| # | 覆盖 | 验证层级 | 验收负责人 | Then | When | Given |",
                    "|---|---|---|---|---|---|---|",
                    f"| AC-1 | AGT-003.1 | 接口 | @PO | {then} | 调用能力 | 有效输入 |",
                ]))
                self.lint._check_coverage(self.path, tables, {"AGT-003.1": 1}, set(), "AGT-003", 1, {"coverage": {}})
                self.assertEqual(self.codes(), expected)


    def test_cross_document_reference_must_exist_in_target(self):
        self.lint._defs_cache[self.reqs["QA-001"]["path"]] = {"AC-1", "M-1"}
        for ref, expected in (("QA-001：AC-1", []), ("QA-001：M-1", []), ("QA-001：AC-2", ["RF07"])):
            with self.subTest(ref=ref):
                self.lint.findings.clear()
                self.lint._check_references(self.path, [ref], 1, {}, "AGT-003", self.reqs, 1)
                self.assertEqual(self.codes(), expected)


class VerificationLevelTests(unittest.TestCase):
    def run_level(self, lint, level):
        tables = parse_tables(mask_lines([
            "### 11.1 端到端验收",
            "| # | 覆盖 | 验证层级 | Given | When | Then |",
            "|---|---|---|---|---|---|",
            f"| AC-1 | ABC-001.1 | {level} | 前提 | 操作 | 结果 |",
        ]))
        lint._check_coverage("x.md", tables, {"ABC-001.1": 1}, set(), "ABC-001", 1, {"coverage": {}})
        return [f.code for f in lint.findings]

    def test_core_levels_exclude_domain_levels_until_project_declares_them(self):
        lint = Linter("review")
        lint.verify_levels = set(prd_lint.CORE_VERIFY_LEVELS)
        self.assertEqual(self.run_level(lint, "接口"), [])
        self.assertEqual(self.run_level(lint, "链路段"), ["CV02"])
        lint.findings.clear()
        lint.verify_levels.add("链路段")
        self.assertEqual(self.run_level(lint, "链路段"), [])


@unittest.skipIf(MODULE_PREFIX, "项目已登记模块前缀，不使用通用需求 ID 形态")
class ReservedPrefixTests(unittest.TestCase):
    def test_quality_and_decision_ids_are_not_requirement_ids(self):
        self.assertEqual(REQ_ID_PATTERN.findall("MET-001 EVAL-001 AP-001 ADR-001 ABC-001"), ["ABC-001"])


class EffectReferenceTests(unittest.TestCase):
    def setUp(self):
        self.lint = Linter("review")
        self.lint.plans = {
            ("AP-001", "1.0"): {"fm": {"status": "superseded"}, "th": {"TH-1": "MET-001"}},
            ("AP-001", "1.1"): {"fm": {"status": "draft"}, "th": {"TH-1": "MET-001", "TH-2": "MET-002"}},
        }

    def run_effect(self, metric_rows, plan_row="| AP-001 | 1.1 | EVAL-001 | |", rank=1):
        self.lint.findings.clear()
        tables = parse_tables(mask_lines([
            "### 12.1 验收方案与评测协议",
            "| 验收方案 | 版本 | 评测集 | 说明 |", "|---|---|---|---|", plan_row, "",
            "### 12.2 红线", "| # | 红线 | 判定方式 | 来源 |", "|---|---|---|---|", "| RL-1 | 越权 | 人工 | CTX |", "",
            "### 12.3 质量指标", "| # | 指标 ID | 测量方式 | 门槛引用 | 来源 |", "|---|---|---|---|---|", *metric_rows, "",
            "### 12.5 Bad Case", "| # | 输入 | 现状表现 | 期望表现 | 来源 |", "|---|---|---|---|---|", "| BC-1 | a | b | c | SRC-1 |",
        ]))
        self.lint._check_effect("x.md", tables, rank)
        return [(f.code, f.level) for f in self.lint.findings]

    def test_valid_reference_and_pending_threshold_pass(self):
        self.assertEqual(self.run_effect(["| M-1 | MET-001 | 评测 | AP-001 · 1.1 · TH-1 | CTX |",
                                          "| M-2 | MET-002 | 评测 | [待定] | CTX |"]), [])

    def test_unresolvable_references_are_rejected(self):
        for ref, metric in (("AP-001 · 2.0 · TH-1", "MET-001"), ("AP-001 · 1.1 · TH-9", "MET-001"),
                            ("AP-001 · 1.1 · TH-2", "MET-001"), ("AP-009 · 1.0 · TH-1", "MET-001")):
            with self.subTest(ref=ref):
                self.assertEqual(self.run_effect([f"| M-1 | {metric} | 评测 | {ref} | CTX |"]), [("EF06", "error")])

    def test_malformed_reference_and_legacy_threshold_columns(self):
        self.assertEqual(self.run_effect(["| M-1 | MET-001 | 评测 | 0.8 | CTX |"]), [("EF03", "error")])
        self.lint.findings.clear()
        tables = parse_tables(["| # | 指标 ID | Demo 基线 | 波动范围 | 上线门槛 | 来源 |", "|---|---|---|---|---|---|",
                               "| M-1 | MET-001 | 0.7 | 0.02 | 0.8 | CTX |"])
        self.lint._check_effect("x.md", tables, 0)
        self.assertIn(("EF03", "warn"), [(f.code, f.level) for f in self.lint.findings])

    def test_plan_reference_required_and_superseded_warns(self):
        self.assertIn(("EF01", "error"), self.run_effect(["| M-1 | MET-001 | 评测 | [待定] | CTX |"], plan_row="| | | | |"))
        self.assertEqual(self.run_effect(["| M-1 | MET-001 | 评测 | AP-001 · 1.0 · TH-1 | CTX |"]), [("EF06", "warn")])

    def test_frozen_requirement_only_notes_unfrozen_plan(self):
        self.assertEqual(self.run_effect(["| M-1 | MET-001 | 评测 | AP-001 · 1.1 · TH-1 | CTX |"], rank=2), [("EF05", "info")])


PLAN = """---
id: AP-001
title: 测试方案
version: "{ver}"
status: {status}
scope_kind: requirement
scope: {scope}
requirements: [ABC-001]
owner: "@PO"
supersedes: ""
updated: 2026-09-29
---

## 4. 门槛

| 条目 | 指标 ID | 评测集 · 版本 | 基线 | 波动范围 | 门槛 | 来源 |
|---|---|---|---|---|---|---|
| TH-1 | MET-001 | EVAL-001 · 1.0 | 0.70 | 0.02 | {threshold} | {source} |
"""


class PlanTests(unittest.TestCase):
    def check(self, *plans):
        with tempfile.TemporaryDirectory(dir=ROOT) as d:
            for i, kw in enumerate(plans):
                args = {"ver": "1.0", "status": "draft", "scope": "ABC-001", "threshold": "0.80", "source": "SRC-1", **kw}
                Path(d, f"AP-001-测试-{i}.md").write_text(PLAN.format(**args), encoding="utf-8")
            with mock.patch.object(prd_lint, "PLAN_DIR", Path(d)):
                lint = Linter(None)
                lint.metric_ids, lint.eval_ids = {"MET-001"}, {"EVAL-001"}
                lint.plans = load_plans()
                check_plans(lint, {"ABC-001": {}})
        return sorted({f.code for f in lint.findings})

    def test_valid_plan_passes(self):
        self.assertEqual(self.check({}), [])
        self.assertEqual(self.check({"status": "frozen"}), [])

    def test_frozen_plan_rejects_pending_values_and_proposals(self):
        self.assertEqual(self.check({"status": "frozen", "threshold": "[待定]"}), ["AP03"])
        self.assertEqual(self.check({"status": "frozen", "source": "提案"}), ["AP03"])

    def test_requirement_scope_must_match(self):
        self.assertEqual(self.check({"scope": "P0 首批"}), ["AP01"])

    def test_version_conflicts(self):
        self.assertEqual(self.check({}, {}), ["AP04"])
        self.assertEqual(self.check({"status": "frozen"}, {"ver": "1.1", "status": "frozen"}), ["AP04"])
        self.assertEqual(self.check({"status": "superseded"}, {"ver": "1.1", "status": "frozen"}), [])


CONTEXT = """---
title: 术语表
---

## 2. 业务概念

| 术语 | 定义 | 禁用同义词 | 来源 |
|---|---|---|---|
| 审批单 | 申请的载体 | 申请表 | {src} |
| `[待补充/术语: 其他术语 — @待定]` | | | |
| | | | |
"""


class ContextSourceTests(unittest.TestCase):
    def check(self, src, ps=("PS-1",), qs=None):
        with tempfile.TemporaryDirectory(dir=ROOT) as d:
            f = Path(d, "glossary.md")
            f.write_text(CONTEXT.format(src=src), encoding="utf-8")
            with mock.patch.object(prd_lint, "context_files", lambda: [f]), \
                 mock.patch.object(prd_lint, "load_context_registry", lambda: (set(ps), qs or {"Q-1": "采用审批单", "Q-2": "未决"})):
                lint = Linter(None)
                check_context(lint)
        return [(f.code, f.level) for f in lint.findings]

    def test_registered_sources_and_proposals_pass(self):
        for src in ("PS-1", "Q-1", "提案", "PS-1、Q-1"):
            with self.subTest(src=src):
                self.assertEqual(self.check(src), [])

    def test_invalid_or_unregistered_sources(self):
        self.assertEqual(self.check(""), [("CX01", "warn")])
        self.assertEqual(self.check("CTX"), [("CX01", "warn")])
        self.assertEqual(self.check("SRC-1"), [("CX01", "warn")])
        self.assertEqual(self.check("PS-9"), [("CX02", "error")])
        self.assertEqual(self.check("Q-9"), [("CX02", "error")])
        self.assertEqual(self.check("Q-2"), [("CX03", "warn")])


class PackageTests(unittest.TestCase):
    """Skill 与项目骨架作为一个整体可用。"""

    def run_script(self, name, *args):
        return subprocess.run([sys.executable, str(SKILL / "scripts" / name), *args], cwd=_PROJECT,
                              capture_output=True, text=True, env={**os.environ, "PRD_ROOT": str(_PROJECT)})

    def test_fresh_project_passes_lint_and_status_check(self):
        r = self.run_script("prd_lint.py")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("错误 0", r.stdout)
        r = self.run_script("generate_status.py", "--check")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_versions_are_consistent(self):
        spec = prd_lint.spec_version()
        self.assertEqual(prd_lint.LINT_SPEC_VERSION, spec)
        fm = split_frontmatter((SKILL / "templates" / "project" / "00-context" / "project.md").read_text(encoding="utf-8"))[0]
        self.assertEqual(fm["framework_version"], spec)
        fm = split_frontmatter((SKILL / "templates" / "requirement-prd.md").read_text(encoding="utf-8"))[0]
        self.assertEqual(fm["template_version"], spec)
        for stage in (SKILL / "stages").glob("*.md"):
            self.assertIn(f"适配规范版本：**{spec}**", stage.read_text(encoding="utf-8"), stage.name)

    def test_skill_frontmatter_follows_agent_skills_spec(self):
        fm = split_frontmatter((SKILL / "SKILL.md").read_text(encoding="utf-8"))[0]
        self.assertEqual(fm["name"], SKILL.name)
        self.assertRegex(fm["name"], r"^[a-z0-9]+(-[a-z0-9]+)*$")
        self.assertLessEqual(len(fm["description"]), 1024)
        self.assertLessEqual(len(fm.get("compatibility", "")), 500)
        allowed = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
        self.assertLessEqual(set(fm), allowed)

    def test_skill_documents_reference_existing_files(self):
        """Skill 文档中以反引号引用的 Skill 内路径均存在。"""
        prefixes = ("core/", "stages/", "templates/", "references/", "scripts/", "domain-packs/_TEMPLATE")
        missing = []
        for doc in list(SKILL.rglob("*.md")) + [REPO / "README.md"]:
            if "templates/project" in doc.as_posix():
                continue
            for m in re.finditer(r"`([^`\s<>*]+)`", doc.read_text(encoding="utf-8")):
                path = m.group(1).split("#")[0].rstrip("/")
                if path.startswith(prefixes) and not (SKILL / path).exists():
                    missing.append(f"{doc.relative_to(REPO)}: {path}")
        self.assertEqual(missing, [])

    def test_no_private_names_in_package(self):
        """维护者可在仓库根目录的 .private-names（不纳入版本控制）中逐行列出不得公开的名称。"""
        names_file = REPO / ".private-names"
        names = [n.strip() for n in names_file.read_text(encoding="utf-8").splitlines()
                 if n.strip() and not n.startswith("#")] if names_file.exists() else []
        if not names:
            self.skipTest("未配置 .private-names")
        pattern = re.compile("|".join(re.escape(n) for n in names))
        hits = [str(p.relative_to(REPO)) for p in [*(REPO / "skills").rglob("*"), REPO / "README.md"]
                if p.is_file() and pattern.search(p.read_text(encoding="utf-8", errors="ignore"))]
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
