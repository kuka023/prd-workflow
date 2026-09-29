#!/usr/bin/env python3
"""生成根目录下的 status.md、open-questions.md、decisions.md，并做需求库一致性校验。

规范性检查（来源、覆盖率、门禁等）见 scripts/prd_lint.py。

用法:
    python3 scripts/generate_status.py           # 生成文件
    python3 scripts/generate_status.py --check   # 只校验，有问题时退出码 1（供 CI 用）

不依赖第三方库。frontmatter 解析仅支持本项目模板用到的形式：
  key: value
  key: [a, b]
  key: "value"
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import defaultdict
from datetime import date

from prdlib import (  # noqa: E402
    MODULE_NAMES, PENDING_VALUE_PATTERN, REQ_DIR, ROOT, TODO_PATTERN, context_files, context_rows,
    is_content_file, parse_frontmatter,
)

OUT_DIR = ROOT

STATUS_ORDER = ["draft", "review", "frozen", "deprecated"]


# ---------------------------------------------------------------------- git

def git_available() -> bool:
    try:
        subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=ROOT, capture_output=True, check=True,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def git_commits(req_id: str) -> tuple[int, str]:
    """返回 (提交数, 最近提交日期)。"""
    try:
        out = subprocess.run(
            ["git", "log", f"--grep={req_id}", "--date=short", "--format=%ad"],
            cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return 0, "—"
    if not out:
        return 0, "—"
    lines = out.splitlines()
    return len(lines), lines[0]


def code_progress(commits: int, status: str) -> str:
    if status == "deprecated":
        return "已废弃"
    if commits == 0:
        return "未开始"
    return "开发中"


# ------------------------------------------------------------------ 收集数据

def collect_requirements() -> list[dict]:
    reqs = []
    for path in sorted(REQ_DIR.rglob("*.md")):
        if path.name.startswith("_"):
            continue
        text = path.read_text(encoding="utf-8")
        fm = parse_frontmatter(text)
        if not fm.get("id"):
            continue
        todos = TODO_PATTERN.findall(text)
        commits, last_commit = git_commits(fm["id"])
        reqs.append({
            "id": fm["id"],
            "title": fm.get("title", ""),
            "module": fm.get("module", ""),
            "batch": fm.get("batch", ""),
            "status": fm.get("status", "draft"),
            "priority": fm.get("priority", ""),
            "milestone": fm.get("milestone", ""),
            "owner": fm.get("owner", ""),
            "assignee": fm.get("assignee", ""),
            "depends_on": fm.get("depends_on", []) or [],
            "blocks": fm.get("blocks", []) or [],
            "todo_count": len(todos),
            "pending_values": len(PENDING_VALUE_PATTERN.findall(text)),
            "commits": commits,
            "last_commit": last_commit,
            "path": path.relative_to(ROOT).as_posix(),
        })
    return reqs


def collect_open_questions() -> list[tuple[str, int, str]]:
    """扫描全库的 [待补充]，返回 (相对路径, 行号, 内容)。"""
    found = []
    for path in sorted(ROOT.rglob("*.md")):
        rel = path.relative_to(ROOT).as_posix()
        if not is_content_file(rel):
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for match in TODO_PATTERN.finditer(line):
                cat = (match.group(1) or "").strip()
                desc = (match.group(2) or "").strip() or "（未说明）"
                found.append((rel, lineno, f"[{cat}] {desc}" if cat else desc))
    return found


# -------------------------------------------------------------------- 校验

def check(reqs: list[dict]) -> list[str]:
    errors = []
    ids = [r["id"] for r in reqs]

    dupes = {i for i in ids if ids.count(i) > 1}
    for i in sorted(dupes):
        errors.append(f"ID 重复: {i}")

    known = set(ids)
    for r in reqs:
        for field in ("depends_on", "blocks"):
            for ref in r[field]:
                if ref not in known:
                    errors.append(f"{r['id']} 的 {field} 指向不存在的 ID: {ref}")
        if r["status"] not in STATUS_ORDER:
            errors.append(f"{r['id']} 的 status 非法: {r['status']}")
        if r["status"] == "frozen" and r["todo_count"] > 0:
            errors.append(
                f"{r['id']} 状态为 frozen 但仍有 {r['todo_count']} 个 [待补充]"
            )
        if r["commits"] > 0 and r["status"] == "draft":
            errors.append(
                f"{r['id']} 已有 {r['commits']} 个提交，但需求状态仍是 draft（需求未评审就开发？）"
            )

    # 双向依赖一致性（提示而非错误，故也归入 errors 便于暴露）
    by_id = {r["id"]: r for r in reqs}
    for r in reqs:
        for ref in r["depends_on"]:
            target = by_id.get(ref)
            if target and r["id"] not in target["blocks"]:
                errors.append(
                    f"依赖未双向声明: {r['id']}.depends_on 含 {ref}，但 {ref}.blocks 不含 {r['id']}"
                )
    return errors


# ------------------------------------------------------------------ 生成输出

def render_status(reqs: list[dict], errors: list[str], has_git: bool) -> str:
    today = date.today().isoformat()
    total_todo = sum(r["todo_count"] for r in reqs)
    total_pending = sum(r["pending_values"] for r in reqs)

    lines = [
        "<!-- 本文件由 scripts/generate_status.py 自动生成，请勿手改 -->",
        "",
        "# 交付状态",
        "",
        f"生成时间：{today}　|　需求总数：{len(reqs)}",
        "",
        f"需求文件内待补充项：{total_todo}　|　待定数值（`[待定]`/`[待测]`）：{total_pending}",
        "",
        "> 全库（含 context / contracts）的完整待补充台账见 [open-questions.md](open-questions.md)。",
        "",
    ]

    if not has_git:
        lines += [
            "> ⚠️ 当前目录不是 Git 仓库，代码进度与提交统计不可用。",
            "",
        ]

    # 需求成熟度分布
    by_status = defaultdict(list)
    for r in reqs:
        by_status[r["status"]].append(r)
    lines += ["## 需求成熟度", "", "| 状态 | 数量 | 需求 |", "|---|---|---|"]
    for st in STATUS_ORDER:
        group = by_status.get(st, [])
        ids = "、".join(r["id"] for r in group) or "—"
        lines.append(f"| {st} | {len(group)} | {ids} |")
    lines.append("")

    # 全量明细
    lines += [
        "## 需求明细",
        "",
        "| ID | 标题 | 模块 | 当期批次 | 成熟度 | 代码进度 | 提交 | 最近提交 | 待补充 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in sorted(reqs, key=lambda x: x["id"]):
        lines.append(
            f"| [{r['id']}]({r['path']}) | {r['title']} | {r['module']} | {r['batch'] or '—'} | "
            f"{r['status']} | "
            f"{code_progress(r['commits'], r['status'])} | {r['commits']} | {r['last_commit']} | "
            f"{r['todo_count']} |"
        )
    lines.append("")

    # 按当期批次
    by_ms = defaultdict(list)
    for r in reqs:
        by_ms[r["batch"] or "未分配"].append(r)
    lines += ["## 按当期批次", "", "| 批次 | 数量 | 需求 |", "|---|---|---|"]
    for ms in sorted(by_ms):
        group = by_ms[ms]
        lines.append(f"| {ms} | {len(group)} | {'、'.join(r['id'] for r in group)} |")
    lines.append("")

    # 待补充最多的需求
    top = sorted(reqs, key=lambda x: -x["todo_count"])[:8]
    lines += [
        "## 待补充最多的需求",
        "",
        "这张表指向下一步该填哪些文件。",
        "",
        "| ID | 标题 | 待补充 | 待定数值 |",
        "|---|---|---|---|",
    ]
    for r in top:
        lines.append(f"| {r['id']} | {r['title']} | {r['todo_count']} | {r['pending_values']} |")
    lines.append("")

    # 未分配负责人
    unassigned = [r for r in reqs if "待补充" in str(r["assignee"]) or not r["assignee"]]
    lines += [
        "## 未分配开发负责人",
        "",
        ("　".join(r["id"] for r in unassigned) or "无") ,
        "",
    ]

    # 校验结果
    lines += ["## 一致性校验", ""]
    if errors:
        lines.append(f"发现 {len(errors)} 个问题：")
        lines.append("")
        for e in errors:
            lines.append(f"- {e}")
    else:
        lines.append("✅ 无问题")
    lines.append("")

    return "\n".join(lines)


def render_open_questions(items: list[tuple[str, int, str]]) -> str:
    today = date.today().isoformat()
    by_file = defaultdict(list)
    for rel, lineno, desc in items:
        by_file[rel].append((lineno, desc))

    lines = [
        "<!-- 本文件由 scripts/generate_status.py 自动生成，请勿手改 -->",
        "<!-- 要修改某一项，请直接编辑源文件中的 [待补充] 标记 -->",
        "",
        "# 开放问题台账",
        "",
        f"生成时间：{today}　|　总计：{len(items)} 项",
        "",
        "> 格式约定：`[待补充/类别: 问题 — @负责人]`（constitution CN-30）。未写负责人的项无法推进，应优先补上。",
        "",
    ]

    # 带负责人的优先列出
    owned = [(f, l, d) for f, l, d in items if "@" in d]
    lines += [
        "## 已指定负责人",
        "",
        "| 文件 | 行 | 问题 |",
        "|---|---|---|",
    ]
    for rel, lineno, desc in owned:
        lines.append(f"| `{rel}` | {lineno} | {desc} |")
    if not owned:
        lines.append("| — | — | 无 |")
    lines.append("")

    lines += ["## 按文件分布", "", "| 文件 | 待补充数 |", "|---|---|"]
    for rel in sorted(by_file, key=lambda k: -len(by_file[k])):
        lines.append(f"| `{rel}` | {len(by_file[rel])} |")
    lines.append("")

    lines += ["## 全部明细", ""]
    for rel in sorted(by_file):
        lines.append(f"### `{rel}`")
        lines.append("")
        for lineno, desc in by_file[rel]:
            lines.append(f"- L{lineno}: {desc}")
        lines.append("")

    return "\n".join(lines)


# ------------------------------------------------------------------ 决策台账

def _cells(line: str) -> list[str]:
    s = line.strip().strip("|")
    return [c.strip() for c in s.split("|")]


def collect_pending_thresholds() -> list[dict]:
    """验收方案中门槛或基线仍为 [待定] / [待测] 的 TH-n（CN-57）。"""
    out = []
    plan_dir = ROOT / "03-quality" / "acceptance"
    for path in sorted(plan_dir.glob("AP-*.md")) if plan_dir.exists() else []:
        text = path.read_text(encoding="utf-8")
        fm = parse_frontmatter(text)
        if fm.get("status") == "superseded":
            continue
        header = None
        for line in text.splitlines():
            if not line.strip().startswith("|"):
                header = None
                continue
            cells = _cells(line)
            if "条目" in cells and "门槛" in cells:
                header = cells
                continue
            if header and cells and re.fullmatch(r"TH-\d+", cells[0]) and len(cells) >= len(header):
                row = dict(zip(header, cells))
                pending = [k for k in ("基线", "波动范围", "门槛") if re.search(r"\[待(?:定|测)\]", row.get(k, ""))]
                if pending:
                    out.append({"plan": f"{fm.get('id', path.stem)} · {fm.get('version', '')}",
                                "path": path.relative_to(ROOT).as_posix(), "id": cells[0],
                                "metric": row.get("指标 ID", ""), "pending": "、".join(pending),
                                "owner": fm.get("owner", ""), "scope": fm.get("scope", "")})
    return out


def collect_decisions() -> tuple[list[dict], list[dict]]:
    """汇总 04-decisions/ 中的 ADR，以及各需求、验收方案与项目适配（project.md）开放问题表中的 Q-n。"""
    adrs = []
    for path in sorted((ROOT / "04-decisions").glob("ADR-*.md")):
        fm = parse_frontmatter(path.read_text(encoding="utf-8"))
        adrs.append({"id": fm.get("id", path.stem), "title": fm.get("title", ""),
                     "status": fm.get("status", ""), "decider": fm.get("decider", ""),
                     "affects": fm.get("affects", []) or [],
                     "path": path.relative_to(ROOT).as_posix()})
    qs = []
    plan_dir = ROOT / "03-quality" / "acceptance"
    plans = sorted(plan_dir.glob("AP-*.md")) if plan_dir.exists() else []
    project = [p for p in [ROOT / "00-context" / "project.md"] if p.exists()]
    for path in sorted(REQ_DIR.rglob("*.md")) + plans + project:
        if path.name.startswith("_"):
            continue
        text = path.read_text(encoding="utf-8")
        fm = parse_frontmatter(text)
        if path in plans and fm.get("status") == "superseded":
            continue
        rid = "项目适配" if path in project else fm.get("id", "") + (f" · {fm.get('version', '')}" if path in plans else "")
        header = None
        for line in text.splitlines():
            if not line.strip().startswith("|"):
                header = None
                continue
            cells = _cells(line)
            if "建议口径" in cells and "结论" in cells:
                header = cells
                continue
            if header and cells and re.fullmatch(r"Q-\d+", cells[0]) and len(cells) >= len(header):
                row = dict(zip(header, cells))
                qs.append({"req": rid, "path": path.relative_to(ROOT).as_posix(), "id": cells[0],
                           "question": row.get("问题", ""), "category": row.get("类别", ""),
                           "owner": row.get("负责人", ""), "due": row.get("需在何时前答", ""),
                           "blocks": row.get("阻塞什么", ""), "conclusion": row.get("结论", "")})
    return adrs, qs


def _owners(owner: str) -> list[str]:
    parts = [p.strip().lstrip("@").strip() for p in re.split(r"[·、,，]", owner) if p.strip()]
    return parts or ["未指定"]


def render_decisions(adrs: list[dict], qs: list[dict]) -> str:
    today = date.today().isoformat()
    open_q = [q for q in qs if q["conclusion"] in ("", "未决")]
    open_adr = [a for a in adrs if a["status"] != "accepted" and a["status"] != "superseded"]
    lines = [
        "<!-- 本文件由 scripts/generate_status.py 自动生成，请勿手改 -->",
        "<!-- 要修改某一项，请编辑对应需求或验收方案的开放问题表、03-quality/acceptance/ 中的门槛，或 04-decisions/ 中的 ADR -->",
        "",
        "# 决策台账",
        "",
        f"生成时间：{today}　|　未决 ADR：{len(open_adr)}　|　未决开放问题：{len(open_q)} / {len(qs)}",
        "",
        "> 跨需求的决策以 ADR 为准（CN-4）；各需求的开放问题中引用 ADR 的，随 ADR 一并决定。",
        "",
        "## 1. 跨需求决策（ADR）",
        "",
        "| ADR | 标题 | 状态 | 决策方 | 影响的需求 |",
        "|---|---|---|---|---|",
    ]
    for a in adrs:
        lines.append(f"| [{a['id']}]({a['path']}) | {a['title']} | {a['status']} | {a['decider']} | {'、'.join(a['affects'])} |")
    if not adrs:
        lines.append("| — | — | — | — | — |")
    lines.append("")

    by_owner: dict[str, list[dict]] = defaultdict(list)
    for q in open_q:
        for o in _owners(q["owner"]):
            by_owner[o].append(q)
    lines += ["## 2. 按决策方汇总", "", "| 决策方 | 未决问题数 |", "|---|---|"]
    for o in sorted(by_owner, key=lambda k: -len(by_owner[k])):
        lines.append(f"| {o} | {len(by_owner[o])} |")
    lines.append("")

    lines += ["## 3. 按决策方明细", ""]
    for o in sorted(by_owner, key=lambda k: -len(by_owner[k])):
        lines += [f"### {o}", "", "| 需求 | 编号 | 问题 | 类别 | 需在何时前答 | 阻塞什么 |", "|---|---|---|---|---|---|"]
        for q in sorted(by_owner[o], key=lambda x: (x["due"], x["req"], x["id"])):
            lines.append(f"| [{q['req']}]({q['path']}) | {q['id']} | {q['question']} | {q['category']} | {q['due']} | {q['blocks']} |")
        lines.append("")

    pending = collect_pending_thresholds()
    lines += ["## 4. 验收方案中待定的门槛与基线", "",
              "> 门槛由 PO 确定（CN-56、CN-57）；基线由评测负责方测得。功能开发不以此为前提，调优类工作须待方案冻结。", "",
              "| 验收方案 | 条目 | 指标 | 待定项 | 适用范围 | 方案负责人 |", "|---|---|---|---|---|---|"]
    for p in pending:
        lines.append(f"| [{p['plan']}]({p['path']}) | {p['id']} | {p['metric']} | {p['pending']} | {p['scope']} | {p['owner']} |")
    if not pending:
        lines.append("| — | — | — | — | — | — |")
    lines.append("")

    proposals = [(path.relative_to(ROOT).as_posix(), line, key, src)
                 for path in context_files() for line, key, src in context_rows(path) if "提案" in src]
    lines += ["## 5. 项目适配中待确认的提案", "",
              "> 来源为提案的上下文条目尚未确认，需求不得以 CTX 引用（CN-9、CN-21）。确认后将来源改为 PS-n 或 Q-n。", "",
              "| 文件 | 行 | 条目 | 来源 |", "|---|---|---|---|"]
    for f, line, key, src in proposals:
        lines.append(f"| [{f}]({f}#L{line}) | {line} | {key} | {src} |")
    if not proposals:
        lines.append("| — | — | — | — |")
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------- main

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="只校验，不写文件")
    args = parser.parse_args()

    if not REQ_DIR.exists():
        print(f"找不到需求目录: {REQ_DIR}", file=sys.stderr)
        return 2

    has_git = git_available()
    reqs = collect_requirements()
    errors = check(reqs)

    if args.check:
        if errors:
            print(f"一致性校验失败，{len(errors)} 个问题：")
            for e in errors:
                print(f"  - {e}")
            return 1
        print(f"✅ 一致性校验通过（{len(reqs)} 条需求）")
        return 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "status.md").write_text(
        render_status(reqs, errors, has_git), encoding="utf-8"
    )
    questions = collect_open_questions()
    (OUT_DIR / "open-questions.md").write_text(
        render_open_questions(questions), encoding="utf-8"
    )

    print(f"已生成 status.md（{len(reqs)} 条需求）")
    print(f"已生成 open-questions.md（{len(questions)} 个待补充项）")
    adrs, qs = collect_decisions()
    (OUT_DIR / "decisions.md").write_text(render_decisions(adrs, qs), encoding="utf-8")
    print(f"已生成 decisions.md（ADR {len(adrs)} 份，开放问题 {len(qs)} 个）")
    if not has_git:
        print("提示：当前不是 Git 仓库，代码进度列为空。")
    if errors:
        print(f"⚠️ 一致性校验发现 {len(errors)} 个问题，详见 status.md 末尾。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
