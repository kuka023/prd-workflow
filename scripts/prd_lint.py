#!/usr/bin/env python3
"""prd_lint —— 需求库的确定性检查（适配规范版本 1.2）。

凡是能由脚本判定的纪律，由本脚本判定，不依赖模型自觉（constitution CN-55）。

用法:
    python3 scripts/prd_lint.py                          # 检查全库
    python3 scripts/prd_lint.py --file 01-requirements/abc/ABC-001-需求名称.md
    python3 scripts/prd_lint.py --file <文件> --as review # 按目标状态预检：现在提交评审会有哪些问题
    python3 scripts/prd_lint.py --json                   # 机器可读输出，供 Skill 使用
    python3 scripts/prd_lint.py --errors-only

退出码：存在错误时为 1，否则为 0。

严重度随状态变化：多数检查在 draft 状态只给警告，在 review / frozen 状态为错误。
使用 --as 可按目标状态提前检查。

全库检查同时检查验收方案（03-quality/acceptance/AP-nnn-*.md，CN-57）与项目适配条目的来源（CN-9）。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

from prdlib import (
    GUIDANCE_START, ITEM_PATTERN, MODULE_PREFIX, context_files, context_rows, load_context_registry, OBJ_FULL, OBJ_PATTERN, PLAN_DIR, REQ_DIR, REQ_ID, REQ_ID_PATTERN,
    ROOT, TODO_CATEGORIES, TODO_PATTERN, PENDING_VALUE_PATTERN, Table, clean_cell,
    headings, mask_lines, parse_tables, project_config, rel, spec_version, split_frontmatter,
)

LINT_SPEC_VERSION = "1.2"
STATUS_RANK = {"draft": 0, "review": 1, "frozen": 2}
STATUSES = ["draft", "review", "frozen", "deprecated"]
CORE_VERIFY_LEVELS = {"界面", "接口", "数据", "评测"}   # 项目可在 project.md 中新增（CN-8）
PLAN_STATUSES = ["draft", "review", "frozen", "superseded"]
PLAN_RANK = {"draft": 0, "review": 1, "frozen": 2, "superseded": 2}
REQUIRED_PLAN_FM = ["id", "title", "version", "status", "scope_kind", "scope", "requirements", "owner", "updated"]
THRESHOLD_REF = re.compile(r"(AP-\d{3})\s*·\s*v?(\d+(?:\.\d+)*)\s*·\s*(TH-\d+)")
SOURCE_TOKEN = re.compile(r"SRC-\d+|CTX|Q-\d+|提案")
SOURCED_PREFIXES = {"P", "D", "S", "O", "BR", "DR", "EX", "RL", "M", "BC"}
REQUIRED_FM = ["id", "title", "module", "status", "owner", "assignee", "template_version", "updated"]
REQUIRED_CHAPTERS = ["背景与问题", "闭环与范围", "设计结论", "角色与权限", "业务规则",
                     "功能需求", "异常与边界", "功能验收", "开放问题", "附录"]
CODE_HINT = re.compile(
    r"(?<![\w/])(?:src|lib|app|pkg)/[\w./-]+|[\w-]+\.(?:py|ts|tsx|js|jsx|java|go|kt|sql|vue|rb|cs|cpp)\b"
)
PRONOUN = re.compile(r"它们?|他们")
SECTION_REF = re.compile(r"见第\s*[\d一二三四五六七八九十]+\s*[章节]|如上所述|如前所述")
PATH_TOKEN = re.compile(r"`([^`\s]+)`|\]\(([^)\s]+)\)")


@dataclass
class Finding:
    level: str      # error | warn | info
    code: str
    file: str
    line: int
    msg: str


class Linter:
    def __init__(self, as_status: str | None):
        self.as_status = as_status
        self.findings: list[Finding] = []
        self.stats: dict[str, dict] = {}
        self.spec = spec_version()
        self.roles = self._load_roles()
        self.synonyms = self._load_synonyms()
        self.metric_ids, self.eval_ids = self._load_quality_ids()
        extra = project_config().get("verification_levels") or []
        self.verify_levels = CORE_VERIFY_LEVELS | {str(x) for x in (extra if isinstance(extra, list) else [extra])}
        self.plans = load_plans()
        self._defs_cache: dict[Path, set[str] | None] = {}
        self.all_names = {p.name for p in ROOT.rglob("*") if ".git" not in p.parts}

    # ------------------------------------------------------------ 公共工具

    def add(self, level, code, file, line, msg):
        self.findings.append(Finding(level, code, file, line, msg))

    @staticmethod
    def gate(rank: int, at: int = 1) -> str:
        """rank 达到 at 时为错误，否则为警告。"""
        return "error" if rank >= at else "warn"

    def _load_roles(self) -> set[str]:
        path = ROOT / "00-context" / "personas.md"
        if not path.exists():
            return set()
        return set(re.findall(r"\|\s*`?(R-[A-Z]{2,})`?\s*\|", path.read_text(encoding="utf-8")))

    def _load_synonyms(self) -> dict[str, str]:
        path = ROOT / "00-context" / "glossary.md"
        if not path.exists():
            return {}
        text = path.read_text(encoding="utf-8")
        out = {}
        for t in parse_tables(mask_lines(text.splitlines())):
            ci = t.col("禁用同义词")
            if ci is None:
                continue
            for _, cells in t.rows:
                if ci >= len(cells) or "待补充" in cells[0]:
                    continue
                term = clean_cell(cells[0])
                for syn in re.split(r"[、,，]", cells[ci]):
                    syn = syn.strip()
                    if syn and re.search(r"[\u4e00-\u9fff]", syn) and not re.fullmatch(r"[A-Za-z]+", syn):
                        out[syn] = term
        return out

    def _load_quality_ids(self) -> tuple[set[str], set[str]]:
        q = ROOT / "03-quality"
        m = set(re.findall(r"MET-\d{3}", (q / "metrics.md").read_text(encoding="utf-8"))) if (q / "metrics.md").exists() else set()
        e = set(re.findall(r"EVAL-\d{3}", (q / "eval-sets.md").read_text(encoding="utf-8"))) if (q / "eval-sets.md").exists() else set()
        return m, e

    # ------------------------------------------------------ 全库：路径引用

    def check_paths(self, files: list[Path]):
        for path in files:
            r = rel(path)
            text = path.read_text(encoding="utf-8")
            for lineno, line in enumerate(text.splitlines(), 1):
                for m in PATH_TOKEN.finditer(line):
                    token = (m.group(1) or m.group(2) or "").split("#")[0]
                    if not self._looks_like_path(token):
                        continue
                    if not self._path_exists(path, token):
                        self.add("error", "RF03", r, lineno, f"引用的路径不存在：{token}")

    @staticmethod
    def _looks_like_path(token: str) -> bool:
        if not token or token.startswith(("http", "mailto:", "@", "-")):
            return False
        if any(ch in token for ch in "<>*{}$") or "XXX" in token or "nnn" in token:
            return False
        if token.endswith("/"):
            # 目录：只检查含多级路径或编号顶层目录（如 03-quality/）的写法
            d = token.rstrip("/")
            return bool(re.fullmatch(r"[\w.-]+(/[\w.-]+)*", d)) and ("/" in d or bool(re.match(r"\d\d-", d)))
        return bool(re.search(r"\.(md|yaml|yml|py)$", token))

    def _path_exists(self, src: Path, token: str) -> bool:
        t = token.rstrip("/")
        if "/" not in t and not token.endswith("/"):
            return t in self.all_names
        return (src.parent / t).exists() or (ROOT / t).exists()

    # --------------------------------------------------------- 需求文件

    def lint_requirement(self, path: Path, all_reqs: dict[str, dict]):
        r = rel(path)
        text = path.read_text(encoding="utf-8")
        fm, body_start = split_frontmatter(text)
        raw_lines = text.splitlines()
        body_raw = raw_lines[body_start - 1:]
        body = mask_lines(body_raw)
        status = fm.get("status", "draft")
        eff = self.as_status or status
        rank = STATUS_RANK.get(eff, 0)
        stat = {"status": status, "checked_as": eff, "todo_by_category": Counter(),
                "proposals": 0, "coverage": {}}
        self.stats[r] = stat

        self._check_frontmatter(r, fm, path, rank)
        if status == "deprecated":
            return

        self._check_spec_links(r, fm, all_reqs, rank)

        hs = headings(body, body_start)
        if not any(level == 2 for _, level, _ in hs):
            level = "error" if rank >= 1 else "info"
            self.add(level, "ST00", r, body_start, "需求尚未按模板展开")
            return

        tables = parse_tables(body, body_start)
        has_effect = any(level == 2 and "效果验收" in text for _, level, text in hs)

        self._check_acceptance_ownership(r, fm, tables, rank)

        self._check_chapters(r, hs, rank)
        self._check_empty_chapters(r, body, body_start, hs, rank)
        self._check_guidance(r, body_raw, body_start, rank)
        defs, deleted = self._collect_definitions(r, body, body_start, tables, hs, fm.get("id", ""))
        self._check_references(r, body, body_start, defs, fm.get("id", ""), all_reqs, rank)
        self._check_todos(r, body, body_start, tables, rank, stat)
        self._check_sources(r, body, body_start, tables, hs, defs, fm.get("id", ""), rank, stat)
        self._check_questions(r, tables, rank)
        self._check_permission_matrix(r, tables, rank)
        self._check_input_consistency(r, fm.get("id", ""), defs)
        self._check_coverage(r, tables, defs, deleted, fm.get("id", ""), rank, stat)
        if has_effect:
            self._check_effect(r, tables, rank)
        self._check_writing(r, body, body_raw, body_start, tables)

    # frontmatter
    def _check_frontmatter(self, r, fm, path, rank):
        for key in REQUIRED_FM:
            if key not in fm or fm[key] in ("", None):
                if key == "template_version":
                    self.add("error", "FM01", r, 1, "frontmatter 缺少 template_version（CN-50）")
                else:
                    self.add("error", "FM01", r, 1, f"frontmatter 缺少字段：{key}")
        checks = [("module", list(MODULE_PREFIX)), ("status", STATUSES)]
        for key, allowed in checks:
            if fm.get(key) and fm[key] not in allowed:
                self.add("error", "FM02", r, 1, f"{key} 取值非法：{fm[key]}（允许 {' / '.join(allowed)}）")
        batch = str(fm.get("batch", "") or "")
        if batch and not re.fullmatch(r"P\d", batch):
            self.add("error", "FM02", r, 1, f"batch 取值非法：{batch}（如 P0、P1）")
        elif not batch:
            self.add(self.gate(rank), "FM02", r, 1, "未填写 batch（当期批次，CN-49）")
        scale = fm.get("scale", "")
        if scale and scale not in ("B", "C"):
            self.add("error", "FM02", r, 1, f"scale 取值非法：{scale}（B / C；A 级不写 PRD）")
        elif not scale:
            self.add(self.gate(rank), "FM02", r, 1, "未填写 scale（规模分级，CN-45）")
        rid = fm.get("id", "")
        mod = fm.get("module", "")
        if rid and not path.name.startswith(rid):
            self.add("error", "FM03", r, 1, f"文件名与 id 不一致：{rid}")
        if rid and mod in MODULE_PREFIX and not rid.startswith(MODULE_PREFIX[mod] + "-"):
            self.add("error", "FM03", r, 1, f"id 前缀与 module 不一致：{rid} / {mod}")
        if mod and path.parent.name != mod:
            self.add("error", "FM03", r, 1, f"文件所在目录与 module 不一致：{path.parent.name} / {mod}")
        tv = str(fm.get("template_version", ""))
        if tv and tv != self.spec:
            self.add("warn", "FM04", r, 1, f"所依据的规范版本 {tv} 落后于当前版本 {self.spec}（CN-51）")

    # 规格边界与业务验收归属（验收关联不进入开发依赖图）
    def _check_spec_links(self, r, fm, all_reqs, rank):
        kind = fm.get("spec_kind")
        if kind not in ("business", "capability"):
            self.add(self.gate(rank), "SK01", r, 1,
                     "spec_kind 须明确为 business 或 capability；不得从旧 type 字段推断（CN-48）")
        refs = fm.get("business_requirements", [])
        if not isinstance(refs, list) or any(not isinstance(ref, str) for ref in refs):
            self.add(self.gate(rank), "SK02", r, 1, "business_requirements 须为需求 ID 列表（CN-53）")
            return
        if kind != "capability":
            if refs:
                self.add(self.gate(rank), "SK02", r, 1,
                         "仅 capability 使用 business_requirements；业务 PRD 在正文声明自身验收责任（CN-53）")
            return
        if not refs:
            self.add(self.gate(rank), "SK02", r, 1, "能力规格尚未关联承担最终业务验收的 PRD（CN-53）")
        for ref in refs:
            target = all_reqs.get(ref)
            if ref == fm.get("id") or not target or target["fm"].get("spec_kind") != "business" or target["fm"].get("status") == "deprecated":
                self.add(self.gate(rank), "SK02", r, 1,
                         f"业务验收归属无效：{ref}，须指向其他未废弃且明确标为 business 的需求（CN-53）")

    def _check_acceptance_ownership(self, r, fm, tables, rank):
        if fm.get("spec_kind") != "capability":
            return
        refs = fm.get("business_requirements", [])
        if not isinstance(refs, list):
            return  # 字段错误已由 SK02 报告
        required = ("业务 PRD ID", "验收负责人", "业务验收条目引用")
        ownership = [t for t in tables if all(t.col(c) is not None for c in required)]
        for ref in refs:
            if not isinstance(ref, str):
                continue
            rows = [(t, line, cells) for t in ownership for line, cells in t.rows
                    if t.col("业务 PRD ID") < len(cells)
                    and ref in REQ_ID_PATTERN.findall(cells[t.col("业务 PRD ID")])]
            complete = False
            for t, _, cells in rows:
                owner_i, ac_i = t.col("验收负责人"), t.col("业务验收条目引用")
                if max(owner_i, ac_i) < len(cells):
                    complete |= bool(clean_cell(cells[owner_i]) and re.search(r"(?:AC|M)-\d+\b", cells[ac_i]))
            if not complete:
                self.add(self.gate(rank), "SK03", r, rows[0][1] if rows else 1,
                         f"{ref} 缺少业务验收归属行、负责人或 AC-n / M-n 引用（CN-53）；条目有效性由审稿核对")

    # 章节
    def _check_chapters(self, r, hs, rank):
        h2 = [(line, text) for line, level, text in hs if level == 2]
        for kw in REQUIRED_CHAPTERS:
            if not any(kw in text for _, text in h2):
                self.add(self.gate(rank), "ST01", r, 1, f"缺少必填章节：{kw}")

    def _check_empty_chapters(self, r, body, start, hs, rank):
        h2 = [line for line, level, _ in hs if level == 2]
        bounds = h2 + [start + len(body)]
        for a, b in zip(bounds, bounds[1:]):
            content = [l for l in body[a - start + 1: b - start] if l.strip() and l.strip() != "---"
                       and not re.match(r"^#{3,6}\s", l)]
            if not content:
                title = body[a - start].lstrip("# ").strip()
                self.add(self.gate(rank), "ST03", r, a, f"章节无内容：{title}。非必填章节应整章删除，必填章节须填写（CN-48）")

    def _check_guidance(self, r, body_raw, start, rank):
        if rank < 1:
            return
        hits = [i for i, line in enumerate(body_raw) if GUIDANCE_START.match(line)]
        if hits:
            self.add("warn", "ST02", r, start + hits[0], f"残留 {len(hits)} 处模板写作说明，完成后应整块删除（CN-39）")

    # 编号定义
    def _collect_definitions(self, r, body, start, tables, hs, rid):
        defs: dict[str, int] = {}
        deleted: set[str] = set()

        def define(key, line):
            if key in defs:
                self.add("error", "RF02", r, line, f"编号重复定义：{key}（首次定义于 L{defs[key]}）")
            else:
                defs[key] = line

        for t in tables:
            for line, cells in t.rows:
                if not cells:
                    continue
                first = clean_cell(cells[0])
                if OBJ_FULL.fullmatch(first):
                    define(first, line)
                    if "已删除" in " ".join(cells):
                        deleted.add(first)
        for line, level, text in hs:
            m = re.match(r"^(D-\d+)\b", text)
            if m:
                define(m.group(1), line)
        for i, line in enumerate(body):
            m = re.match(r"^\s*[-*]\s+\*\*(" + re.escape(rid) + r"\.\d+)\*\*", line) if rid else None
            if m:
                define(m.group(1), start + i)
                if "已删除" in line:
                    deleted.add(m.group(1))
        return defs, deleted

    # 引用
    def _check_references(self, r, body, start, defs, rid, all_reqs, rank):
        missing = {}
        for i, line in enumerate(body):
            for m in OBJ_PATTERN.finditer(line):
                key = f"{m.group(1)}-{m.group(2)}"
                external = re.search(r"(" + REQ_ID + r")\s*(?:的|中的|[:：])?\s*$", line[:m.start()])
                if external and external.group(1) != rid:
                    self._check_external_ref(r, start + i, external.group(1), key, all_reqs, rank)
                    continue  # 「ABC-001 EX-2」或「ABC-001：AC-2」
                if key not in defs and key not in missing:
                    missing[key] = start + i
            for m in ITEM_PATTERN.finditer(line):
                key = m.group(1)
                if key.startswith(rid + ".") and key not in defs and key not in missing:
                    missing[key] = start + i
            for m in REQ_ID_PATTERN.finditer(line):
                if m.group(1) not in all_reqs and m.group(1) != rid:
                    self.add("warn", "RF05", r, start + i, f"引用了不存在的需求 ID：{m.group(1)}")
            for role in re.findall(r"(?<![A-Za-z0-9-])(R-[A-Z]{2,})\b", line):
                if role not in self.roles and role != "R-XXX":
                    self.add(self.gate(rank), "RF04", r, start + i, f"角色 ID 未在 personas.md 登记：{role}（CN-1）")
            for mid in re.findall(r"MET-\d{3}", line):
                if mid not in self.metric_ids:
                    self.add(self.gate(rank), "RF06", r, start + i, f"指标 ID 未在 03-quality/metrics.md 定义：{mid}")
            for eid in re.findall(r"EVAL-\d{3}", line):
                if eid not in self.eval_ids:
                    self.add(self.gate(rank), "RF06", r, start + i, f"评测集 ID 未在 03-quality/eval-sets.md 登记：{eid}")
        for key, line in missing.items():
            self.add(self.gate(rank), "RF01", r, line, f"引用的编号未定义：{key}")

    def _target_defs(self, path: Path) -> set[str] | None:
        """目标需求中定义的编号；文件不存在或尚未展开时返回 None。"""
        if path not in self._defs_cache:
            defs = None
            if path.exists():
                fm, start = split_frontmatter(path.read_text(encoding="utf-8"))
                body = mask_lines(path.read_text(encoding="utf-8").splitlines()[start - 1:])
                ids = {clean_cell(c[0]) for tb in parse_tables(body, start) for _, c in tb.rows if c}
                defs = {k for k in ids if OBJ_FULL.fullmatch(k)} or None
            self._defs_cache[path] = defs
        return self._defs_cache[path]

    def _check_external_ref(self, r, line, target, key, all_reqs, rank):
        info = all_reqs.get(target)
        if not info:
            return  # 需求不存在由 RF05 报告
        defs = self._target_defs(info["path"])
        if defs is None:
            if info["path"].exists():
                self.add("warn", "RF07", r, line, f"{target} 尚未展开，无法核对跨文件引用 {target}：{key}")
        elif key not in defs:
            self.add(self.gate(rank), "RF07", r, line, f"跨文件引用的编号在目标需求中不存在：{target}：{key}")

    # 待补充
    def _check_todos(self, r, body, start, tables, rank, stat):
        todo_total = 0
        for i, line in enumerate(body):
            for m in TODO_PATTERN.finditer(line):
                todo_total += 1
                cat = (m.group(1) or "").strip()
                desc = (m.group(2) or "").strip()
                stat["todo_by_category"][cat or "未分类"] += 1
                if rank >= 2:
                    self.add("error", "TD01", r, start + i, "frozen 状态不得存在 [待补充]")
                if not cat:
                    self.add(self.gate(rank), "TD02", r, start + i, "待补充未标注类别，格式应为 [待补充/类别: 问题 — @负责人]（CN-30）")
                elif cat not in TODO_CATEGORIES:
                    self.add(self.gate(rank), "TD02", r, start + i, f"待补充类别非法：{cat}（允许 {'、'.join(TODO_CATEGORIES)}）")
                if "@" not in desc:
                    self.add(self.gate(rank), "TD03", r, start + i, "待补充未指定负责人（@负责人，未知时写 @待定）")
            if rank >= 2 and PENDING_VALUE_PATTERN.search(line):
                self.add("error", "TD04", r, start + i, "frozen 状态不得存在 [待定] / [待测]")
        q_rows = sum(len(t.rows) for t in tables if t.col("建议口径") is not None)
        if todo_total > q_rows:
            self.add("warn", "TD05", r, 1, f"正文有 {todo_total} 处待补充，开放问题表只有 {q_rows} 行；每个未知项应有对应的 Q-n 与建议口径（CN-31）")
        stat["todo_total"] = todo_total

    # 来源
    def _check_sources(self, r, body, start, tables, hs, defs, rid, rank, stat):
        q_conclusions = {}
        for t in tables:
            ci, ki = t.col("结论"), t.col("建议口径")
            if ci is None or ki is None:
                continue
            for _, cells in t.rows:
                q = clean_cell(cells[0]) if cells else ""
                if q.startswith("Q-") and ci < len(cells):
                    q_conclusions[q] = clean_cell(cells[ci])

        def validate(value: str, key: str, line: int):
            v = re.sub(r"[（(][^）)]*[）)]", "", clean_cell(value)).strip()
            if not v:
                self.add(self.gate(rank), "SR01", r, line, f"{key} 未标注来源（CN-20）")
                return
            for tok in [x for x in re.split(r"[、,，;；/\s]+", v) if x]:
                if tok == "提案":
                    stat["proposals"] += 1
                    if rank >= 1:
                        self.add("error", "SR03", r, line, f"{key} 的来源为「提案」，review 及以上状态不得存在未决提案（CN-22）")
                elif tok == "CTX":
                    continue
                elif re.fullmatch(r"SRC-\d+", tok):
                    continue
                elif re.fullmatch(r"Q-\d+", tok):
                    concl = q_conclusions.get(tok, "")
                    if not concl or concl in ("未决", "待定"):
                        self.add(self.gate(rank), "SR06", r, line, f"{key} 以 {tok} 为来源，但 {tok} 尚无结论")
                else:
                    self.add(self.gate(rank), "SR02", r, line, f"{key} 的来源取值非法：{tok}（只允许 SRC-n / CTX / Q-n / 提案，CN-21）")

        # 横向表格：首列为编号，且有「来源」列
        for t in tables:
            si = t.col("来源")
            if si is None:
                continue
            for line, cells in t.rows:
                key = clean_cell(cells[0]) if cells else ""
                m = re.fullmatch(r"([A-Z]+)-\d+", key)
                if not m or m.group(1) not in SOURCED_PREFIXES or "已删除" in " ".join(cells):
                    continue
                src = cells[si] if si < len(cells) else ""
                others = " ".join(c for i, c in enumerate(cells) if i != si)
                if not clean_cell(src) and "[待补充" in others:
                    continue  # 条目内容本身为待补充时，来源可留空（CN-20）
                validate(src, key, line)
        # 纵向表格：D-n 下的「来源」行
        for t in tables:
            dm = re.match(r"^(D-\d+)\b", t.section)
            if not dm or t.col("项") is None:
                continue
            row = next(((ln, c) for ln, c in t.rows if c and clean_cell(c[0]) == "来源"), None)
            if row is None:
                self.add(self.gate(rank), "SR01", r, t.line, f"{dm.group(1)} 缺少「来源」行（CN-20）")
            else:
                validate(row[1][1] if len(row[1]) > 1 else "", dm.group(1), row[0])
        # 功能需求条目：行内「（来源：…）」
        if rid:
            for i, line in enumerate(body):
                m = re.match(r"^\s*[-*]\s+\*\*(" + re.escape(rid) + r"\.\d+)\*\*(.*)$", line)
                if not m or "已删除" in line:
                    continue
                sm = re.search(r"来源[:：]\s*((?:[^（）()]|[（(][^（）()]*[）)])*)[）)]?", m.group(2))
                validate(sm.group(1) if sm else "", m.group(1), start + i)

        # 正文中的行内来源（功能条目之外），以及非规定写法的「提案」
        item_re = re.compile(r"^\s*[-*]\s+\*\*[A-Z]+-\d{3}\.\d+\*\*")
        inline_re = re.compile(r"[（(]来源[:：]\s*((?:[^（）()]|[（(][^（）()]*[）)])*)[）)]")
        skip_lines, d_table_lines, source_cell = set(), set(), {}
        for t in tables:
            path = " ".join(t.heading_path)
            if t.col("建议口径") is not None or "本版变更" in path or "修订记录" in path:
                skip_lines |= {ln for ln, _ in t.rows}
                continue
            si = t.col("来源")
            is_d = bool(re.match(r"^D-\d+\b", t.section)) and t.col("项") is not None
            for ln, cells in t.rows:
                if is_d:
                    d_table_lines.add(ln)
                    if cells and clean_cell(cells[0]) == "来源" and len(cells) > 1:
                        source_cell[ln] = cells[1]
                elif si is not None and si < len(cells):
                    source_cell[ln] = cells[si]
        changelog = False
        for i, line in enumerate(body):
            ln = start + i
            h = re.match(r"^#{2,6}\s+(.*)$", line)
            if h:
                changelog = "本版变更" in h.group(1) or "修订记录" in h.group(1)
            if changelog or ln in skip_lines:
                continue
            rest = line.replace(source_cell.get(ln, ""), "") if ln in source_cell else line
            if not item_re.match(line):
                for m in inline_re.finditer(rest):
                    if ln not in d_table_lines:  # 纵向表格只在「来源」行计数（CN-21）
                        validate(m.group(1), f"L{ln} 行内内容", ln)
            rest = inline_re.sub("", rest)
            n = rest.count("提案")
            if n:
                stat["proposals"] += n
                level = "error" if rank >= 1 else "warn"
                self.add(level, "SR07", r, ln, "「提案」未使用规定写法，应写作行内「（来源：提案）」或写入来源列；review 及以上状态不得存在未决提案（CN-21、CN-22）")

    # 开放问题
    def _check_questions(self, r, tables, rank):
        for t in tables:
            ki = t.col("建议口径")
            if ki is None:
                continue
            oi, di = t.col("负责人"), t.col("需在何时前答")
            for line, cells in t.rows:
                q = clean_cell(cells[0]) if cells else ""
                if not q.startswith("Q-") or "已删除" in " ".join(cells):
                    continue
                if not clean_cell(cells[1] if len(cells) > 1 else ""):
                    continue  # 空白模板行
                if ki >= len(cells) or not clean_cell(cells[ki]):
                    self.add(self.gate(rank), "QS01", r, line, f"{q} 未给出建议口径（CN-31）")
                if oi is not None and (oi >= len(cells) or not clean_cell(cells[oi])):
                    self.add(self.gate(rank), "QS02", r, line, f"{q} 未指定负责人（CN-32）")
                if di is not None and (di >= len(cells) or not clean_cell(cells[di])):
                    self.add("warn", "QS02", r, line, f"{q} 未写明答复时限（CN-32）")

    # 权限矩阵
    def _check_permission_matrix(self, r, tables, rank):
        for t in tables:
            if "权限矩阵" not in " ".join(t.heading_path):
                continue
            for line, cells in t.rows:
                if any(clean_cell(c) == "?" for c in cells[1:]):
                    level = "error" if rank >= 2 else ("warn" if rank == 1 else None)
                    if level:
                        self.add(level, "PM01", r, line, "权限矩阵存在 ?，frozen 前须清零")

    # 与素材包的一致性
    def _check_input_consistency(self, r, rid, defs):
        inp = ROOT / "inputs" / rid / "input.md"
        cited = {k for k in defs if k.startswith("SRC-")}
        if not cited:
            return
        if not inp.exists():
            self.add("warn", "SR05", r, 1, f"未找到素材包 inputs/{rid}/input.md，无法核对 SRC 编号（CN-5）")
            return
        registered = set(re.findall(r"SRC-\d+", inp.read_text(encoding="utf-8")))
        for k in sorted(cited - registered):
            self.add("warn", "SR05", r, defs[k], f"{k} 在附录中登记，但素材包中不存在")

    # AC 覆盖
    def _check_coverage(self, r, tables, defs, deleted, rid, rank, stat):
        covered: set[str] = set()
        e2e = [ln for t in tables if "端到端" in " ".join(t.heading_path) and t.col("覆盖") is not None
               and all(t.col(col) is not None for col in ("Given", "When", "Then"))
               for ln, c in t.rows if c and clean_cell(c[0]).startswith("AC-")
               and all(t.col(col) < len(c) and clean_cell(c[t.col(col)]) for col in ("Given", "When", "Then"))]
        if not e2e:
            self.add(self.gate(rank), "CV04", r, 1, "缺少完整的端到端验收条目：须验证本文业务或能力边界，并填写 Given / When / Then（CN-44）；语义完整性由审稿核对")
        for t in tables:
            ci, vi = t.col("覆盖"), t.col("验证层级")
            if ci is None:
                continue
            for line, cells in t.rows:
                ac = clean_cell(cells[0]) if cells else ""
                if not ac.startswith("AC-") or "已删除" in " ".join(cells):
                    continue
                cov = cells[ci] if ci < len(cells) else ""
                refs = {f"{a}-{b}" for a, b in OBJ_PATTERN.findall(cov)} | set(ITEM_PATTERN.findall(cov))
                if not refs:
                    self.add(self.gate(rank), "CV03", r, line, f"{ac} 未填写覆盖的编号")
                covered |= refs
                lv = clean_cell(cells[vi]) if vi is not None and vi < len(cells) else ""
                if lv not in self.verify_levels:
                    self.add(self.gate(rank), "CV02", r, line,
                             f"{ac} 的验证层级为空或非法：「{lv}」（允许 {' / '.join(sorted(self.verify_levels))}；"
                             "新增层级在 00-context/project.md 声明，CN-8）")
        groups = {"功能条目": lambda k: k.startswith(rid + "."), "BR": lambda k: k.startswith("BR-"),
                  "DR": lambda k: k.startswith("DR-"), "EX": lambda k: k.startswith("EX-")}
        for name, pred in groups.items():
            items = [k for k in defs if pred(k) and k not in deleted]
            unc = [k for k in items if k not in covered]
            stat["coverage"][name] = f"{len(items) - len(unc)}/{len(items)}"
            for k in unc:
                self.add(self.gate(rank), "CV01", r, defs[k], f"{k} 没有任何 AC 覆盖")

    # 效果验收（含该章节时）
    def _check_effect(self, r, tables, rank):
        def rows_with(prefix):
            return [(ln, c) for t in tables for ln, c in t.rows
                    if c and re.fullmatch(prefix + r"-\d+", clean_cell(c[0])) and clean_cell(c[1] if len(c) > 1 else "")]

        # 验收方案引用（CN-57）
        plan_rows = [(ln, c, t) for t in tables if t.col("验收方案") is not None for ln, c in t.rows
                     if re.search(r"AP-\d{3}", c[t.col("验收方案")] if t.col("验收方案") < len(c) else "")]
        if rank >= 1 and not plan_rows:
            self.add("error", "EF01", r, 1, "未引用验收方案（AP-nnn）；门槛、基线与评测集登记在验收方案中（CN-3、CN-57）")
        for line, cells, t in plan_rows:
            pid = re.search(r"AP-\d{3}", cells[t.col("验收方案")]).group(0)
            vi = t.col("版本")
            ver = clean_cell(cells[vi]) if vi is not None and vi < len(cells) else ""
            versions = {v for (i, v) in self.plans if i == pid}
            if not versions:
                self.add(self.gate(rank), "EF06", r, line, f"验收方案不存在：{pid}")
            elif ver and ver not in versions:
                self.add(self.gate(rank), "EF06", r, line, f"验收方案 {pid} 不存在版本 {ver}（现有 {'、'.join(sorted(versions))}）")
            elif not ver:
                self.add(self.gate(rank), "EF06", r, line, f"引用验收方案 {pid} 未注明版本（CN-57）")

        if rank >= 1:
            for prefix, name, code in (("RL", "红线", "EF02"), ("M", "质量指标", "EF03"), ("BC", "Bad Case", "EF04")):
                if not rows_with(prefix):
                    self.add("error", code, r, 1, f"缺少{name}（{prefix}-n）")

        for t in tables:
            if t.col("上线门槛") is not None or t.col("Demo 基线") is not None:
                self.add(self.gate(rank), "EF03", r, t.line,
                         "质量指标表仍含基线或门槛数值列；1.2 起门槛与基线写在验收方案中，本表改为「门槛引用」（CN-3、CN-57）")
            ti, mi = t.col("门槛引用"), t.col("指标 ID")
            if ti is None:
                continue
            for line, cells in t.rows:
                key = clean_cell(cells[0]) if cells else ""
                if not key.startswith("M-") or "已删除" in " ".join(cells):
                    continue
                ref = cells[ti] if ti < len(cells) else ""
                metric = clean_cell(cells[mi]) if mi is not None and mi < len(cells) else ""
                m = THRESHOLD_REF.search(ref)
                if not m:
                    if not PENDING_VALUE_PATTERN.search(ref):
                        self.add(self.gate(rank), "EF03", r, line,
                                 f"{key} 的门槛引用应写作「方案 ID · 版本 · TH-n」，未定时写 [待定]（CN-57）")
                    continue
                pid, ver, th = m.groups()
                plan = self.plans.get((pid, ver))
                if plan is None:
                    self.add(self.gate(rank), "EF06", r, line, f"{key} 引用的验收方案版本不存在：{pid} · {ver}")
                    continue
                if th not in plan["th"]:
                    self.add(self.gate(rank), "EF06", r, line, f"{key} 引用的门槛条目不存在：{pid} · {ver} · {th}")
                elif metric and plan["th"][th] and plan["th"][th] != metric:
                    self.add(self.gate(rank), "EF06", r, line,
                             f"{key} 的指标 {metric} 与 {pid} · {ver} · {th} 的指标 {plan['th'][th]} 不一致（CN-57）")
                if plan["fm"].get("status") == "superseded":
                    self.add("warn", "EF06", r, line, f"{key} 引用的 {pid} · {ver} 已被新版本取代")
                elif rank >= 2 and plan["fm"].get("status") != "frozen":
                    self.add("info", "EF05", r, line,
                             f"{pid} · {ver} 尚未冻结：功能开发可以开工，调优类工作须待方案冻结（CN-56）")

    # 写作
    def _check_writing(self, r, body, body_raw, start, tables):
        rule_lines = set()
        for t in tables:
            if t.col("规则") is not None or t.col("系统行为") is not None:
                rule_lines |= {ln for ln, _ in t.rows}
        syn_hits = Counter()
        syn_first = {}
        for i, line in enumerate(body):
            ln = start + i
            if CODE_HINT.search(line) and not re.search(r"\.(md|yaml|yml)\b", CODE_HINT.search(line).group(0)):
                self.add("warn", "WR01", r, ln, f"疑似代码路径或文件名：{CODE_HINT.search(line).group(0)}（需求不写实现，CN-36）")
            is_item = re.match(r"^\s*[-*]\s+\*\*[A-Z]+-\d{3}\.\d+\*\*", line)
            if (is_item or ln in rule_lines) and PRONOUN.search(line):
                self.add("warn", "WR02", r, ln, "规则或功能条目中使用了代词，应写出主语全称（CN-35）")
            if SECTION_REF.search(line):
                self.add("warn", "WR04", r, ln, "使用了章节号或「如上所述」式引用，应改为编号引用（CN-13）")
            for syn in self.synonyms:
                if syn in line:
                    syn_hits[syn] += line.count(syn)
                    syn_first.setdefault(syn, ln)
        for syn, n in syn_hits.items():
            self.add("warn", "WR03", r, syn_first[syn], f"使用了禁用同义词「{syn}」{n} 次，术语表统一用「{self.synonyms[syn]}」")
        for i, line in enumerate(body_raw):
            m = re.match(r"^\s*```(\w+)", line)
            if m and m.group(1).lower() not in ("text", "mermaid", "markdown", "md", "json", "yaml"):
                self.add("warn", "WR01", r, start + i, f"需求中出现 {m.group(1)} 代码块（需求不写实现，CN-36）")


# ------------------------------------------------------------ 验收方案

def load_plans() -> dict[tuple[str, str], dict]:
    """{(方案 ID, 版本): {path, fm, th: {TH-n: 指标 ID}, th_lines, tables}}（CN-57）。"""
    out: dict[tuple[str, str], dict] = {}
    if not PLAN_DIR.exists():
        return out
    for path in sorted(PLAN_DIR.glob("AP-*.md")):
        text = path.read_text(encoding="utf-8")
        fm, start = split_frontmatter(text)
        tables = parse_tables(mask_lines(text.splitlines()[start - 1:]), start)
        th, th_lines = {}, {}
        for tb in tables:
            if tb.col("条目") is None:
                continue
            mi = tb.col("指标 ID")
            for line, cells in tb.rows:
                k = clean_cell(cells[0]) if cells else ""
                if re.fullmatch(r"TH-\d+", k):
                    th_lines.setdefault(k, []).append(line)
                    th[k] = clean_cell(cells[mi]) if mi is not None and mi < len(cells) else ""
        key = (str(fm.get("id", "")), str(fm.get("version", "")))
        out.setdefault(key, {"path": path, "fm": fm, "th": th, "th_lines": th_lines, "tables": tables, "dupes": []})
        out[key]["dupes"].append(path)
    return out


def check_plans(lint: Linter, reqs: dict[str, dict]):
    frozen_by_id = defaultdict(list)
    for (pid, ver), plan in lint.plans.items():
        r, fm = rel(plan["path"]), plan["fm"]
        status = str(fm.get("status", ""))
        rank = PLAN_RANK.get(status, 0)
        for key in REQUIRED_PLAN_FM:
            if fm.get(key) in ("", None, []):
                lint.add("error", "AP01", r, 1, f"验收方案 frontmatter 缺少字段：{key}")
        if pid and not re.fullmatch(r"AP-\d{3}", pid):
            lint.add("error", "AP01", r, 1, f"验收方案 ID 格式应为 AP-nnn：{pid}")
        if pid and not plan["path"].name.startswith(pid):
            lint.add("error", "AP01", r, 1, f"文件名与 id 不一致：{pid}")
        if status and status not in PLAN_STATUSES:
            lint.add("error", "AP01", r, 1, f"status 取值非法：{status}（允许 {' / '.join(PLAN_STATUSES)}）")
        kind = fm.get("scope_kind", "")
        if kind and kind not in ("requirement", "batch"):
            lint.add("error", "AP01", r, 1, f"scope_kind 取值非法：{kind}（requirement / batch）")
        if len(plan["dupes"]) > 1:
            lint.add("error", "AP04", r, 1, f"验收方案版本重复：{pid} · {ver}（{', '.join(rel(p) for p in plan['dupes'])}）")
        if status == "frozen":
            frozen_by_id[pid].append(ver)
        sup = str(fm.get("supersedes", "") or "")
        if sup:
            m = re.fullmatch(r"(AP-\d{3})\s*·\s*v?(\d+(?:\.\d+)*)", sup.strip())
            if not m or (m.group(1), m.group(2)) not in lint.plans:
                lint.add("warn", "AP04", r, 1, f"supersedes 指向的方案版本不存在：{sup}")
        # 覆盖的需求
        req_list = fm.get("requirements") or []
        req_list = req_list if isinstance(req_list, list) else [req_list]
        for rid in req_list:
            if rid not in reqs:
                lint.add(lint.gate(rank), "AP02", r, 1, f"requirements 指向不存在的需求：{rid}")
        if kind == "requirement" and req_list and (len(req_list) != 1 or fm.get("scope") != req_list[0]):
            lint.add("error", "AP01", r, 1, "scope_kind 为 requirement 时，scope 须为 requirements 中唯一的需求 ID")
        # 门槛条目
        if not plan["th"]:
            lint.add(lint.gate(rank), "AP03", r, 1, "验收方案没有门槛条目（TH-n）")
        for k, lines in plan["th_lines"].items():
            if len(lines) > 1:
                lint.add("error", "AP03", r, lines[1], f"门槛条目重复定义：{k}")
        for tb in plan["tables"]:
            if tb.col("条目") is None:
                continue
            for line, cells in tb.rows:
                k = clean_cell(cells[0]) if cells else ""
                if not re.fullmatch(r"TH-\d+", k):
                    continue
                vals = {h: clean_cell(cells[tb.col(h)]) if tb.col(h) is not None and tb.col(h) < len(cells) else ""
                        for h in ("指标 ID", "评测集 · 版本", "基线", "波动范围", "门槛", "来源")}
                for h, v in vals.items():
                    if not v and h != "来源":
                        lint.add(lint.gate(rank), "AP03", r, line, f"{k} 的「{h}」为空，未知时写 [待测] 或 [待定]")
                if vals["指标 ID"] and vals["指标 ID"] not in lint.metric_ids:
                    lint.add(lint.gate(rank), "AP02", r, line, f"{k} 的指标 ID 未在 03-quality/metrics.md 定义：{vals['指标 ID']}")
                for eid in re.findall(r"EVAL-\d{3}", vals["评测集 · 版本"]):
                    if eid not in lint.eval_ids:
                        lint.add(lint.gate(rank), "AP02", r, line, f"{k} 的评测集未在 03-quality/eval-sets.md 登记：{eid}")
                if rank >= 2 and status == "frozen" and any(PENDING_VALUE_PATTERN.search(cells[i]) for i in range(len(cells))):
                    lint.add("error", "AP03", r, line, f"已冻结的验收方案不得存在 [待定] / [待测]：{k}（CN-57）")
                toks = [x for x in re.split(r"[、,，;；/\s]+", re.sub(r"[（(][^）)]*[）)]", "", vals["来源"])) if x]
                if not toks:
                    lint.add(lint.gate(rank), "AP03", r, line, f"{k} 未标注来源（CN-20）")
                for tok in toks:
                    if not SOURCE_TOKEN.fullmatch(tok):
                        lint.add(lint.gate(rank), "AP03", r, line, f"{k} 的来源取值非法：{tok}（CN-21）")
                    elif tok == "提案" and status == "frozen":
                        lint.add("error", "AP03", r, line, f"已冻结的验收方案不得以「提案」为来源：{k}（CN-22）")
    for pid, vers in frozen_by_id.items():
        if len(vers) > 1:
            lint.add("error", "AP04", rel(lint.plans[(pid, vers[0])]["path"]), 1,
                     f"{pid} 同时存在多个冻结版本（{'、'.join(vers)}）；旧版本应改为 superseded（CN-57）")


# ------------------------------------------------------------ 项目适配

def check_context(lint: Linter):
    ps, qs = load_context_registry()
    for path in context_files():
        r = rel(path)
        for line, key, src in context_rows(path):
            toks = [x for x in re.split(r"[、,，;；/\s]+", re.sub(r"[（(][^）)]*[）)]", "", src)) if x]
            if not toks:
                lint.add("warn", "CX01", r, line, f"项目适配条目「{key}」未标注来源（CN-9）")
            for tok in toks:
                if re.fullmatch(r"PS-\d+", tok):
                    if tok not in ps:
                        lint.add("error", "CX02", r, line, f"「{key}」的来源 {tok} 未在 00-context/sources.md 登记")
                elif re.fullmatch(r"Q-\d+", tok):
                    if tok not in qs:
                        lint.add("error", "CX02", r, line, f"「{key}」的来源 {tok} 不在 00-context/project.md 的待确认事项表中")
                    elif qs[tok] in ("", "未决", "待定"):
                        lint.add("warn", "CX03", r, line, f"「{key}」以 {tok} 为来源，但 {tok} 尚无结论")
                elif tok != "提案":
                    lint.add("warn", "CX01", r, line, f"「{key}」的来源取值非法：{tok}（项目适配只允许 PS-n / Q-n / 提案，CN-9）")


# ---------------------------------------------------------------- 全库检查

def collect_requirements() -> dict[str, dict]:
    out = {}
    for path in sorted(REQ_DIR.rglob("*.md")):
        if path.name.startswith("_"):
            continue
        fm, _ = split_frontmatter(path.read_text(encoding="utf-8"))
        if fm.get("id"):
            out.setdefault(fm["id"], {"path": path, "fm": fm, "dupes": []})["dupes"].append(path)
    return out


def check_dependencies(lint: Linter, reqs: dict[str, dict]):
    for rid, info in reqs.items():
        r = rel(info["path"])
        if len(info["dupes"]) > 1:
            lint.add("error", "FM05", r, 1, f"需求 ID 重复：{rid}（{', '.join(rel(p) for p in info['dupes'])}）")
        fm = info["fm"]
        rank = STATUS_RANK.get(lint.as_status or fm.get("status", "draft"), 0)
        for field in ("depends_on", "blocks"):
            for ref in fm.get(field) or []:
                if ref not in reqs:
                    lint.add("error", "DP01", r, 1, f"{field} 指向不存在的需求：{ref}")
        for ref in fm.get("depends_on") or []:
            if ref in reqs and rid not in (reqs[ref]["fm"].get("blocks") or []):
                lint.add(lint.gate(rank), "DP02", r, 1, f"依赖未双向声明：depends_on 含 {ref}，但 {ref}.blocks 不含 {rid}")
    # 依赖环
    graph = {rid: [d for d in (info["fm"].get("depends_on") or []) if d in reqs] for rid, info in reqs.items()}
    color, stack = {}, []

    def dfs(n):
        color[n] = 1
        stack.append(n)
        for m in graph[n]:
            if color.get(m) == 1:
                cyc = stack[stack.index(m):] + [m]
                lint.add("error", "DP03", rel(reqs[n]["path"]), 1, f"存在依赖环：{' → '.join(cyc)}")
            elif not color.get(m):
                dfs(m)
        stack.pop()
        color[n] = 2

    for n in graph:
        if not color.get(n):
            dfs(n)


def render_text(lint: Linter, errors_only: bool) -> str:
    by_file = defaultdict(list)
    for f in lint.findings:
        if errors_only and f.level != "error":
            continue
        by_file[f.file].append(f)
    icon = {"error": "✗", "warn": "!", "info": "·"}
    out = [f"prd_lint · 规范版本 {lint.spec}" + (f" · 按 {lint.as_status} 状态检查" if lint.as_status else "")]
    if lint.spec != LINT_SPEC_VERSION:
        out.append(f"! 本脚本适配规范版本 {LINT_SPEC_VERSION}，与当前 constitution 版本 {lint.spec} 不一致，请同步更新脚本（CN-50）")
    for file in sorted(by_file):
        out.append("")
        st = lint.stats.get(file)
        suffix = f"  [{st['status']}" + (f" → 按 {st['checked_as']} 检查" if st["checked_as"] != st["status"] else "") + "]" if st else ""
        out.append(file + suffix)
        for f in sorted(by_file[file], key=lambda x: (x.line, x.code)):
            out.append(f"  {icon[f.level]} L{f.line:<4} {f.code}  {f.msg}")
    counts = Counter(f.level for f in lint.findings)
    out.append("")
    out.append(f"汇总：错误 {counts['error']} · 警告 {counts['warn']} · 提示 {counts['info']}")
    for file, st in sorted(lint.stats.items()):
        extra = []
        if st.get("todo_total"):
            extra.append("待补充 " + "、".join(f"{k} {v}" for k, v in st["todo_by_category"].most_common()))
        if st["proposals"]:
            extra.append(f"提案 {st['proposals']}")
        if st["coverage"]:
            extra.append("AC 覆盖 " + "、".join(f"{k} {v}" for k, v in st["coverage"].items()))
        if extra:
            out.append(f"  {file}：" + "；".join(extra))
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description="需求库确定性检查")
    ap.add_argument("--file", action="append", help="只检查指定需求文件（可重复）")
    ap.add_argument("--as", dest="as_status", choices=["draft", "review", "frozen"], help="按目标状态检查")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--errors-only", action="store_true", help="只输出错误")
    args = ap.parse_args()

    lint = Linter(args.as_status)
    reqs = collect_requirements()

    targets = [info["path"] for info in reqs.values()]
    if args.file:
        wanted = {(ROOT / f).resolve() if not Path(f).is_absolute() else Path(f).resolve() for f in args.file}
        missing = [f for f in args.file if not Path(f).exists() and not (ROOT / f).exists()]
        if missing:
            print(f"找不到文件：{', '.join(missing)}", file=sys.stderr)
            return 2
        targets = [p for p in targets if p.resolve() in wanted]
        if not targets:
            print("指定的文件不是带 id 的需求文件", file=sys.stderr)
            return 2
    else:
        lint.check_paths([p for p in ROOT.rglob("*.md")
                          if ".git" not in p.parts and not rel(p).startswith("pilot-history/")
                          and rel(p) not in ("status.md", "open-questions.md", "decisions.md")])
        check_plans(lint, reqs)
        check_context(lint)

    check_dependencies(lint, reqs)
    for path in targets:
        lint.lint_requirement(path, reqs)
    if args.file:
        lint.check_paths(targets)
        scope = {rel(p) for p in targets}
        lint.findings = [f for f in lint.findings if f.file in scope]

    if args.json:
        data = {
            "spec_version": lint.spec,
            "checked_as": args.as_status,
            "findings": [asdict(f) for f in lint.findings],
            "stats": {k: {**v, "todo_by_category": dict(v["todo_by_category"])} for k, v in lint.stats.items()},
            "summary": dict(Counter(f.level for f in lint.findings)),
        }
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(render_text(lint, args.errors_only))
    return 1 if any(f.level == "error" for f in lint.findings) else 0


if __name__ == "__main__":
    sys.exit(main())
