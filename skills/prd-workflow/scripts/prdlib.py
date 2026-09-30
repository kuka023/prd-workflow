"""需求库脚本的公共定义：路径、正则、frontmatter 解析、Markdown 表格解析。

被 generate_status.py 与 prd_lint.py 共用。不依赖第三方库。

两个根目录：
- SKILL_ROOT：本 Skill 所在目录（核心层：规范、模板、脚本）；
- ROOT：项目需求库目录（项目适配、需求、素材、案例）。依次取环境变量 PRD_ROOT、
  从当前目录向上查找含 00-context/project.md 的目录、当前目录。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
CONSTITUTION = SKILL_ROOT / "core" / "constitution.md"


def find_project_root() -> Path:
    env = os.environ.get("PRD_ROOT")
    if env:
        return Path(env).resolve()
    here = Path.cwd().resolve()
    for d in [here, *here.parents]:
        if (d / "00-context" / "project.md").exists():
            return d
    return here


ROOT = find_project_root()
REQ_DIR = ROOT / "01-requirements"
PLAN_DIR = ROOT / "03-quality" / "acceptance"

def load_modules() -> dict[str, tuple[str, str]]:
    """从 00-context/modules.md 读取 {模块: (前缀, 名称)}（CN-10）。"""
    path = ROOT / "00-context" / "modules.md"
    out: dict[str, tuple[str, str]] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        cells = [c.strip().strip("`") for c in line.strip().strip("|").split("|")]
        if len(cells) >= 3 and re.fullmatch(r"[a-z][a-z0-9_]*", cells[0]) and re.fullmatch(r"[A-Z]{2,6}", cells[1]):
            out[cells[0]] = (cells[1], cells[2])
    return out


MODULES = load_modules()
MODULE_PREFIX = {k: v[0] for k, v in MODULES.items()}
MODULE_NAMES = {k: v[1] for k, v in MODULES.items()}
# 模块未登记时退回通用形态，但排除指标、评测集、验收方案、决策记录的编号前缀
RESERVED_PREFIXES = ["MET", "EVAL", "AP", "ADR"]
REQ_ID = r"(?:" + ("|".join(sorted(MODULE_PREFIX.values(), key=len, reverse=True))
                  or r"(?!(?:" + "|".join(RESERVED_PREFIXES) + r")-)[A-Z]{2,6}") + r")-\d{3}"
REQ_ID_PATTERN = re.compile(rf"(?<![A-Za-z0-9-])({REQ_ID})(?![\d])")
ITEM_PATTERN = re.compile(rf"(?<![A-Za-z0-9-])({REQ_ID}\.\d+)(?![\d])")

# [待补充] / [待补充: 描述] / [待补充/类别: 描述 — @负责人]
TODO_PATTERN = re.compile(r"\[待补充(?:/([^:：\]]+))?(?:[:：]\s*([^\]]*))?\]")
PENDING_VALUE_PATTERN = re.compile(r"\[待(?:定|测)\]")

TODO_CATEGORIES = [
    "问题定义", "范围", "权限", "流程", "规则", "数据",
    "异常", "指标", "非功能", "依赖", "术语", "素材",
]

# 需求文件内的编号对象（constitution CN-11）
OBJ_PREFIXES = ["STOP", "SRC", "DEP", "UJ", "BR", "DR", "EX", "AC", "RL", "BC", "P", "D", "S", "O", "M", "Q"]
OBJ_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_-])(" + "|".join(OBJ_PREFIXES) + r")-(\d+)(?![\d.])"
)
OBJ_FULL = re.compile(r"(?:" + "|".join(OBJ_PREFIXES) + r")-\d+")

# 不属于「需求库内容」的文件：规则说明、模板、Skill、案例。
# 这些文件中的 [待补充] 多为格式示例，不计入开放问题台账。
NON_CONTENT = ["README.md", "CLAUDE.md", "AGENTS.md", "status.md", "open-questions.md", "decisions.md"]
NON_CONTENT_DIRS = [".claude/", "cases/", "scripts/", ".git/", "pilot-history/", "domain-packs/"]


def is_content_file(rel: str) -> bool:
    if rel in NON_CONTENT:
        return False
    if any(rel.startswith(d) for d in NON_CONTENT_DIRS):
        return False
    if Path(rel).name.startswith("_TEMPLATE"):
        return False
    return True


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def spec_version() -> str:
    """核心规范版本（本 Skill 中 constitution 的 version）。"""
    fm = parse_frontmatter(CONSTITUTION.read_text(encoding="utf-8"))
    return str(fm.get("version", ""))


def project_config() -> dict:
    """读取 00-context/project.md 的项目声明（CN-8）；文件不存在时返回空字典。"""
    path = ROOT / "00-context" / "project.md"
    return parse_frontmatter(path.read_text(encoding="utf-8")) if path.exists() else {}


# ---------------------------------------------------------------- frontmatter

def parse_scalar(raw: str):
    raw = raw.strip()
    if raw.startswith(("\"", "'")):
        quote = raw[0]
        end = raw.find(quote, 1)
        return raw[1:end] if end != -1 else raw[1:]
    if " #" in raw:
        raw = raw.split(" #", 1)[0].strip()
    elif raw.startswith("#"):
        raw = ""
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        if not inner:
            return []
        return [p.strip().strip("\"'") for p in inner.split(",") if p.strip()]
    return raw


def split_frontmatter(text: str) -> tuple[dict, int]:
    """返回 (frontmatter 字典, 正文起始行号，从 1 计)。"""
    if not text.startswith("---"):
        return {}, 1
    end = text.find("\n---", 3)
    if end == -1:
        return {}, 1
    data = {}
    for line in text[3:end].splitlines():
        s = line.strip()
        if not s or s.startswith("#") or ":" not in s:
            continue
        key, _, raw = s.partition(":")
        data[key.strip()] = parse_scalar(raw)
    body_start = text[: end + 4].count("\n") + 2
    return data, body_start


def parse_frontmatter(text: str) -> dict:
    return split_frontmatter(text)[0]


# ------------------------------------------------------------------ Markdown

GUIDANCE_START = re.compile(r"^>\s*\*\*写作说明")


def mask_lines(lines: list[str]) -> list[str]:
    """将 HTML 注释、围栏代码块、模板写作说明块的内容替换为空串，保留行号。"""
    out = []
    in_comment = False
    in_fence = False
    in_guide = False
    for line in lines:
        s = line
        if in_guide and not s.startswith(">"):
            in_guide = False
        if not in_comment and not in_fence and GUIDANCE_START.match(s):
            in_guide = True
        if in_guide:
            out.append("")
            continue
        if in_fence:
            if s.strip().startswith("```"):
                in_fence = False
            out.append("")
            continue
        if not in_comment and s.strip().startswith("```"):
            in_fence = True
            out.append("")
            continue
        buf = ""
        i = 0
        while i < len(s):
            if in_comment:
                j = s.find("-->", i)
                if j == -1:
                    i = len(s)
                else:
                    in_comment = False
                    i = j + 3
            else:
                j = s.find("<!--", i)
                if j == -1:
                    buf += s[i:]
                    i = len(s)
                else:
                    buf += s[i:j]
                    in_comment = True
                    i = j + 4
        out.append(buf)
    return out


SOURCE_ID = re.compile(r"(?:SRC|PS)-\d+")
SOURCE_VALUE = re.compile(r"(?:SRC|PS|Q)-\d+|CTX|提案")


def source_values(value: str) -> list[str]:
    """把来源单元格拆为来源取值。出现在 SRC-n / PS-n 之后、且不是来源取值的词视为位置说明（如 `SRC-1 §2.1、§8`），不计为取值。"""
    v = re.sub(r"[（(][^）)]*[）)]", "", value).strip().strip("`")
    out, seen_id = [], False
    for word in re.split(r"[、,，;；/\s]+", v):
        if not word:
            continue
        if SOURCE_VALUE.fullmatch(word) or not seen_id:
            out.append(word)
            seen_id = seen_id or bool(SOURCE_ID.fullmatch(word))
    return out


def clean_cell(cell: str) -> str:
    return cell.strip().strip("`").replace("**", "").strip()


@dataclass
class Table:
    header: list[str]
    rows: list[tuple[int, list[str]]]      # (行号, 单元格)
    line: int                              # 表头行号
    section: str                           # 所在最近一级标题文本
    heading_path: list[str] = field(default_factory=list)

    def col(self, name: str) -> int | None:
        for i, h in enumerate(self.header):
            if clean_cell(h) == name:
                return i
        return None


def split_row(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def parse_tables(lines: list[str], start: int = 1) -> list[Table]:
    """lines 为已 mask 的正文行；start 为 lines[0] 的行号。"""
    tables = []
    headings: dict[int, str] = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            level = len(m.group(1))
            headings = {k: v for k, v in headings.items() if k < level}
            headings[level] = m.group(2).strip()
        if line.strip().startswith("|") and i + 1 < len(lines) and re.match(
            r"^\s*\|?\s*:?-{3,}", lines[i + 1]
        ):
            header = split_row(line)
            rows = []
            j = i + 2
            while j < len(lines) and lines[j].strip().startswith("|"):
                rows.append((start + j, split_row(lines[j])))
                j += 1
            path = [headings[k] for k in sorted(headings)]
            tables.append(Table(header, rows, start + i, path[-1] if path else "", path))
            i = j
            continue
        i += 1
    return tables


def headings(lines: list[str], start: int = 1) -> list[tuple[int, int, str]]:
    """返回 (行号, 级别, 标题文本)。"""
    out = []
    for i, line in enumerate(lines):
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            out.append((start + i, len(m.group(1)), m.group(2).strip()))
    return out


# ------------------------------------------------------------ 项目适配（CN-9）

CONTEXT_EXCLUDE = {"project.md", "sources.md", "learned-rules.md"}


def context_files() -> list[Path]:
    """需要标注来源的项目适配文件（CN-9）。"""
    files = [p for p in sorted((ROOT / "00-context").glob("*.md")) if p.name not in CONTEXT_EXCLUDE]
    files += sorted((ROOT / "02-contracts").glob("*.md"))
    files += sorted((ROOT / "03-quality").glob("*.md"))
    return [p for p in files if p.exists() and not p.name.startswith("_")]


def load_context_registry() -> tuple[set[str], dict[str, str]]:
    """返回 (sources.md 中登记的 PS-n, project.md 待确认事项 {Q-n: 结论})。"""
    ps: set[str] = set()
    src = ROOT / "00-context" / "sources.md"
    if src.exists():
        text = src.read_text(encoding="utf-8")
        _, start = split_frontmatter(text)
        for tb in parse_tables(mask_lines(text.splitlines()[start - 1:]), start):
            ps |= {clean_cell(c[0]) for _, c in tb.rows if c and re.fullmatch(r"PS-\d+", clean_cell(c[0]))}
    qs: dict[str, str] = {}
    proj = ROOT / "00-context" / "project.md"
    if proj.exists():
        text = proj.read_text(encoding="utf-8")
        _, start = split_frontmatter(text)
        for tb in parse_tables(mask_lines(text.splitlines()[start - 1:]), start):
            ci = tb.col("结论")
            if tb.col("建议口径") is None or ci is None:
                continue
            for _, c in tb.rows:
                q = clean_cell(c[0]) if c else ""
                if re.fullmatch(r"Q-\d+", q):
                    qs[q] = clean_cell(c[ci]) if ci < len(c) else ""
    return ps, qs


def context_rows(path: Path):
    """逐行产出 (行号, 条目, 来源单元格)；跳过空白模板行与内容为待补充且未填来源的行。"""
    text = path.read_text(encoding="utf-8")
    _, start = split_frontmatter(text)
    for tb in parse_tables(mask_lines(text.splitlines()[start - 1:]), start):
        si = tb.col("来源")
        if si is None:
            continue
        for line, cells in tb.rows:
            others = [clean_cell(c) for i, c in enumerate(cells) if i != si]
            src = clean_cell(cells[si]) if si < len(cells) else ""
            if not any(others) or (not src and any("[待补充" in c or "待补充/" in c for c in cells)):
                continue
            if any("已停用" in c or "已删除" in c for c in cells):
                continue
            yield line, (others[0] if others else ""), src
