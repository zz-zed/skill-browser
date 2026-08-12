#!/usr/bin/env python3
"""Read-only inventory and fact extraction for locally installed Agent Skills."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence


MAX_SKILL_BYTES = 2 * 1024 * 1024
SELF_NAME = "skill-browser"
FORMAT_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])\.(svg|png|jpe?g|webp|html?|md|pdf|docx|xlsx|pptx|drawio|json|csv)\b",
    re.IGNORECASE,
)
HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
FRONTMATTER_KEY_PATTERN = re.compile(r"^([A-Za-z0-9_-]+):(?:\s*(.*))?$")
MARKDOWN_LINK_PATTERN = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
INLINE_CODE_PATTERN = re.compile(r"`([^`]+)`")
TABLE_SEPARATOR_PATTERN = re.compile(r"^:?-{3,}:?$")


OPTION_CATEGORY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("recommendation", ("recommended", "combination", "preset", "推荐", "组合", "预设")),
    ("visual", ("style", "theme", "palette", "visual", "art", "tone", "风格", "主题", "配色", "视觉")),
    ("output", ("output", "format", "aspect", "scale", "size", "ratio", "输出", "格式", "比例", "尺寸")),
    ("runtime", ("backend", "provider", "model", "engine", "runtime", "后端", "引擎", "模型")),
    ("input", ("input", "reference", "language", "lang", "输入", "参考", "语言")),
    ("structure", ("layout", "structure", "diagram type", "supported type", "布局", "结构", "图类型")),
    ("advanced", ("option", "parameter", "configuration", "setting", "advanced", "gallery", "选项", "参数", "配置", "高级")),
)
OPTION_GATE_KEYWORDS = (
    "option",
    "parameter",
    "configuration",
    "setting",
    "gallery",
    "preset",
    "recommended combination",
    "supported diagram type",
    "supported type",
    "选项",
    "参数",
    "配置",
    "预设",
    "推荐组合",
    "支持类型",
    "图类型",
)


@dataclass(frozen=True)
class RootSpec:
    path: Path
    label: str
    scope: str
    hosts: tuple[str, ...]


class ScanFailure(Exception):
    """Expected scanner error that should be rendered without a traceback."""


def expand(path: Path) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(str(path))))


def read_text_bounded(path: Path) -> str:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ScanFailure(f"cannot stat {path}: {exc}") from exc
    if size > MAX_SKILL_BYTES:
        raise ScanFailure(f"file exceeds {MAX_SKILL_BYTES} bytes: {path}")
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ScanFailure(f"file is not valid UTF-8: {path}") from exc
    except OSError as exc:
        raise ScanFailure(f"cannot read {path}: {exc}") from exc


def unquote_yaml_scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value[1:-1]
    if len(value) >= 2 and value[0] == value[-1] == "'":
        return value[1:-1].replace("''", "'")
    return value


def parse_frontmatter(text: str) -> tuple[dict[str, str], str, list[str]]:
    normalized = text.lstrip("\ufeff")
    lines = normalized.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, normalized, ["missing YAML frontmatter"]

    closing = next((index for index in range(1, len(lines)) if lines[index].strip() == "---"), None)
    if closing is None:
        return {}, normalized, ["unterminated YAML frontmatter"]

    raw = lines[1:closing]
    parsed: dict[str, str] = {}
    warnings: list[str] = []
    index = 0
    while index < len(raw):
        line = raw[index]
        match = FRONTMATTER_KEY_PATTERN.match(line)
        if not match:
            index += 1
            continue
        key = match.group(1)
        value = (match.group(2) or "").strip()
        if value in {"|", ">", "|-", ">-", "|+", ">+"}:
            folded = value.startswith(">")
            block: list[str] = []
            index += 1
            while index < len(raw):
                next_line = raw[index]
                if next_line and not next_line[0].isspace():
                    break
                block.append(next_line.strip())
                index += 1
            parsed[key] = (" " if folded else "\n").join(part for part in block if part)
            continue
        parsed[key] = unquote_yaml_scalar(value)
        index += 1

    for required in ("name", "description"):
        if not parsed.get(required):
            warnings.append(f"missing frontmatter field: {required}")
    body = "\n".join(lines[closing + 1 :])
    return parsed, body, warnings


def clean_markdown(value: str) -> str:
    value = value.strip().strip("|").strip()
    value = re.sub(r"\*\*([^*]+)\*\*", r"\1", value)
    value = re.sub(r"__([^_]+)__", r"\1", value)
    value = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", value)
    value = value.replace("`", "")
    return re.sub(r"\s+", " ", value).strip()


def parse_sections(body: str) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    current: Optional[dict[str, Any]] = None
    heading_stack: list[dict[str, Any]] = []
    for line_number, line in enumerate(body.splitlines(), start=1):
        match = HEADING_PATTERN.match(line)
        if match:
            if current is not None:
                current["body"] = "\n".join(current.pop("lines")).strip()
                sections.append(current)
            level = len(match.group(1))
            title = clean_markdown(match.group(2))
            heading_stack = [heading for heading in heading_stack if heading["level"] < level]
            current = {
                "level": level,
                "title": title,
                "line": line_number,
                "path": [heading["title"] for heading in heading_stack] + [title],
                "lines": [],
            }
            heading_stack.append({"level": level, "title": title})
        elif current is not None:
            current["lines"].append(line)
    if current is not None:
        current["body"] = "\n".join(current.pop("lines")).strip()
        sections.append(current)
    return sections


def split_table_row(line: str) -> list[str]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [clean_markdown(cell.replace("\\|", "|")) for cell in re.split(r"(?<!\\)\|", stripped)]


def is_separator_row(cells: Sequence[str]) -> bool:
    return bool(cells) and all(TABLE_SEPARATOR_PATTERN.match(cell.replace(" ", "")) for cell in cells)


def parse_tables(section_body: str) -> list[dict[str, Any]]:
    lines = section_body.splitlines()
    tables: list[dict[str, Any]] = []
    index = 0
    while index + 1 < len(lines):
        if "|" not in lines[index] or "|" not in lines[index + 1]:
            index += 1
            continue
        headers = split_table_row(lines[index])
        separator = split_table_row(lines[index + 1])
        if len(headers) < 2 or len(separator) != len(headers) or not is_separator_row(separator):
            index += 1
            continue
        rows: list[dict[str, str]] = []
        index += 2
        while index < len(lines) and "|" in lines[index]:
            cells = split_table_row(lines[index])
            if len(cells) < len(headers):
                cells.extend([""] * (len(headers) - len(cells)))
            rows.append({headers[pos] or f"column_{pos + 1}": cells[pos] for pos in range(len(headers))})
            index += 1
        tables.append({"headers": headers, "rows": rows})
    return tables


def parse_bullets(section_body: str) -> list[str]:
    bullets: list[str] = []
    for line in section_body.splitlines():
        match = re.match(r"^\s*(?:[-*+] |\d+[.)] )(.+)$", line)
        if not match:
            continue
        value = clean_markdown(match.group(1))
        if value and value not in bullets:
            bullets.append(value)
    return bullets


def contains_keyword(text: str, keyword: str) -> bool:
    lowered = text.casefold()
    keyword = keyword.casefold()
    if any("\u3400" <= character <= "\u9fff" for character in keyword):
        return keyword in lowered
    return re.search(rf"(?<![a-z0-9]){re.escape(keyword)}s?(?![a-z0-9])", lowered) is not None


def option_category(section: dict[str, Any]) -> Optional[str]:
    if re.match(r"^step\s+\d+", section["title"], re.IGNORECASE):
        return None
    path_text = " > ".join(section.get("path") or [section["title"]])
    if not any(contains_keyword(path_text, keyword) for keyword in OPTION_GATE_KEYWORDS):
        return None
    for category, keywords in OPTION_CATEGORY_RULES:
        if any(contains_keyword(path_text, keyword) for keyword in keywords):
            return category
    return "advanced"


def extract_option_groups(sections: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    seen: set[str] = set()
    for section in sections:
        category = option_category(section)
        if category is None:
            continue
        tables = parse_tables(section["body"])
        bullets = parse_bullets(section["body"])
        inline_values = []
        if not tables and not bullets:
            inline_values = [clean_markdown(value) for value in INLINE_CODE_PATTERN.findall(section["body"])]
        if not tables and not bullets and not inline_values:
            continue
        group = {
            "category": category,
            "section": section["title"],
            "section_path": section.get("path") or [section["title"]],
            "source_line": section["line"],
            "tables": tables,
            "bullets": bullets,
            "inline_values": list(dict.fromkeys(value for value in inline_values if value)),
        }
        fingerprint = json.dumps(group, ensure_ascii=False, sort_keys=True)
        if fingerprint not in seen:
            seen.add(fingerprint)
            groups.append(group)
    return groups


def extract_references(skill_dir: Path, body: str) -> list[dict[str, Any]]:
    references: list[dict[str, Any]] = []
    seen: set[str] = set()
    canonical_skill_dir = skill_dir.resolve(strict=True)
    for raw_target in MARKDOWN_LINK_PATTERN.findall(body):
        target = raw_target.split("#", 1)[0].strip()
        if not target or "://" in target or target.startswith("#"):
            continue
        candidate = (skill_dir / target).resolve(strict=False)
        try:
            candidate.relative_to(canonical_skill_dir)
        except ValueError:
            key = f"blocked:{target}"
            if key not in seen:
                seen.add(key)
                references.append({"target": target, "blocked": "outside-skill-directory"})
            continue
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        references.append({"target": target, "path": key, "exists": candidate.is_file()})
    return references


def evidence_lines(sections: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    keywords = ("output", "handoff", "deliver", "limit", "input", "supported", "输出", "交付", "限制", "输入", "支持")
    for section in sections:
        if not any(keyword in section["title"].casefold() for keyword in keywords):
            continue
        lines = [clean_markdown(line) for line in section["body"].splitlines() if clean_markdown(line)]
        if lines:
            evidence.append({"section": section["title"], "line": section["line"], "excerpt": lines[:8]})
    return evidence


def parse_skill(skill_dir: Path) -> dict[str, Any]:
    skill_md = skill_dir / "SKILL.md"
    text = read_text_bounded(skill_md)
    frontmatter, body, warnings = parse_frontmatter(text)
    sections = parse_sections(body)
    name = frontmatter.get("name") or skill_dir.name
    resource_dirs = {
        resource: (skill_dir / resource).is_dir()
        for resource in ("scripts", "references", "assets", "agents", "tests", "evals")
    }
    mentioned_formats = sorted({match.group(1).lower() for match in FORMAT_PATTERN.finditer(body)})
    return {
        "name": name,
        "folder_name": skill_dir.name,
        "description": frontmatter.get("description", ""),
        "frontmatter_keys": sorted(frontmatter),
        "skill_md": str(skill_md),
        "source_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "sections": [{key: section[key] for key in ("level", "title", "line", "path")} for section in sections],
        "option_groups": extract_option_groups(sections),
        "resources": resource_dirs,
        "references": extract_references(skill_dir, body),
        "mentioned_formats": mentioned_formats,
        "evidence_sections": evidence_lines(sections),
        "parse_warnings": warnings,
    }


def ancestor_chain(cwd: Path, stop: Path) -> list[Path]:
    chain = []
    current = cwd
    while True:
        chain.append(current)
        if current == stop or current.parent == current:
            return chain
        current = current.parent


def repository_root(cwd: Path) -> Path:
    current = cwd
    while True:
        if (current / ".git").exists():
            return current
        if current.parent == current:
            return cwd
        current = current.parent


def default_roots(cwd: Path) -> list[RootSpec]:
    home = Path.home()
    roots = [
        RootSpec(home / ".agents" / "skills", "user-shared", "user", ("codex",)),
        RootSpec(home / ".codex" / "skills", "user-codex", "user", ("codex",)),
        RootSpec(home / ".claude" / "skills", "user-claude", "user", ("claude",)),
    ]
    repo_root = repository_root(cwd)
    for directory in ancestor_chain(cwd, repo_root):
        roots.extend(
            (
                RootSpec(directory / ".agents" / "skills", f"project-shared:{directory}", "project", ("codex",)),
                RootSpec(directory / ".claude" / "skills", f"project-claude:{directory}", "project", ("claude",)),
            )
        )
    return roots


def candidate_directories(root: RootSpec, warnings: list[dict[str, str]]) -> Iterable[Path]:
    if not root.path.exists():
        return []
    if not root.path.is_dir():
        warnings.append({"root": str(root.path), "warning": "scan root is not a directory"})
        return []
    candidates: list[Path] = []
    try:
        entries = sorted(root.path.iterdir(), key=lambda item: item.name.casefold())
    except OSError as exc:
        warnings.append({"root": str(root.path), "warning": f"cannot list root: {exc}"})
        return []
    for entry in entries:
        if entry.name.startswith("."):
            continue
        if entry.is_symlink() and not entry.exists():
            warnings.append({"root": str(root.path), "warning": f"broken symlink: {entry}"})
            continue
        if entry.is_dir() and (entry / "SKILL.md").is_file():
            candidates.append(entry)
    return candidates


def merge_location(record: dict[str, Any], root: RootSpec, visible_path: Path) -> None:
    location = {
        "path": str(visible_path),
        "root": str(root.path),
        "label": root.label,
        "scope": root.scope,
        "hosts": list(root.hosts),
        "symlink": visible_path.is_symlink(),
    }
    if location not in record["locations"]:
        record["locations"].append(location)
    record["hosts"] = sorted(set(record["hosts"]).union(root.hosts))
    record["scopes"] = sorted(set(record["scopes"]).union({root.scope}))


def scan_skills(
    cwd: Path,
    host: str = "all",
    extra_roots: Optional[Sequence[Path]] = None,
    include_self: bool = False,
) -> dict[str, Any]:
    roots = default_roots(cwd)
    for index, path in enumerate(extra_roots or (), start=1):
        roots.append(RootSpec(expand(path), f"custom-{index}", "custom", ("codex", "claude")))

    unique_roots: list[RootSpec] = []
    root_keys: set[tuple[str, tuple[str, ...]]] = set()
    for root in roots:
        normalized = expand(root.path)
        key = (str(normalized), root.hosts)
        if key not in root_keys:
            root_keys.add(key)
            unique_roots.append(RootSpec(normalized, root.label, root.scope, root.hosts))

    records_by_path: dict[str, dict[str, Any]] = {}
    scan_warnings: list[dict[str, str]] = []
    for root in unique_roots:
        for visible_dir in candidate_directories(root, scan_warnings):
            try:
                canonical_dir = visible_dir.resolve(strict=True)
            except OSError as exc:
                scan_warnings.append({"root": str(root.path), "warning": f"cannot resolve {visible_dir}: {exc}"})
                continue
            key = str(canonical_dir)
            if key in records_by_path:
                merge_location(records_by_path[key], root, visible_dir)
                continue
            try:
                parsed = parse_skill(canonical_dir)
            except ScanFailure as exc:
                scan_warnings.append({"root": str(root.path), "warning": str(exc)})
                continue
            if not include_self and parsed["name"] == SELF_NAME:
                continue
            record = {
                "id": key,
                "canonical_path": key,
                **parsed,
                "locations": [],
                "hosts": [],
                "scopes": [],
                "name_conflict": [],
            }
            merge_location(record, root, visible_dir)
            records_by_path[key] = record

    records = list(records_by_path.values())
    conflicts: dict[str, list[dict[str, str]]] = {}
    by_name: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        by_name.setdefault(record["name"], []).append(record)
    for name, group in by_name.items():
        if len(group) < 2:
            continue
        choices = [{"id": item["id"], "canonical_path": item["canonical_path"]} for item in group]
        conflicts[name] = choices
        for item in group:
            item["name_conflict"] = [choice for choice in choices if choice["id"] != item["id"]]

    if host != "all":
        records = [record for record in records if host in record["hosts"]]
    records.sort(key=lambda record: (record["name"].casefold(), record["canonical_path"]))
    return {
        "schema_version": 1,
        "generated_from": "live-filesystem-scan",
        "cwd": str(cwd),
        "host_filter": host,
        "roots": [
            {"path": str(root.path), "label": root.label, "scope": root.scope, "hosts": list(root.hosts)}
            for root in unique_roots
        ],
        "skills": records,
        "conflicts": conflicts,
        "warnings": scan_warnings,
    }


def select_skill(inventory: dict[str, Any], selector: str) -> dict[str, Any]:
    exact = [record for record in inventory["skills"] if record["name"] == selector or record["id"] == selector]
    if not exact:
        exact = [record for record in inventory["skills"] if record["folder_name"] == selector]
    if not exact:
        raise ScanFailure(f"Skill not found: {selector}")
    if len(exact) > 1:
        choices = ", ".join(record["canonical_path"] for record in exact)
        raise ScanFailure(f"Skill name is ambiguous; use its canonical path: {choices}")
    return exact[0]


def query_tokens(query: str) -> list[str]:
    lowered = query.casefold().strip()
    tokens = re.findall(r"[a-z0-9][a-z0-9_.+-]*|[\u3400-\u9fff]{2,}", lowered)
    return list(dict.fromkeys([lowered, *tokens])) if lowered else []


def search_records(inventory: dict[str, Any], query: str, limit: int = 10) -> list[dict[str, Any]]:
    tokens = query_tokens(query)
    results: list[dict[str, Any]] = []
    for record in inventory["skills"]:
        name = record["name"].casefold()
        description = record["description"].casefold()
        headings = " ".join(section["title"] for section in record["sections"]).casefold()
        score = 0
        matches: list[str] = []
        for token in tokens:
            if not token:
                continue
            if token == name:
                score += 20
                matches.append(f"exact name: {token}")
            elif token in name:
                score += 10
                matches.append(f"name: {token}")
            if token in description:
                score += 5
                matches.append(f"description: {token}")
            if token in headings:
                score += 2
                matches.append(f"heading: {token}")
        if score:
            results.append(
                {
                    "name": record["name"],
                    "id": record["id"],
                    "description": record["description"],
                    "hosts": record["hosts"],
                    "score": score,
                    "matches": list(dict.fromkeys(matches)),
                }
            )
    results.sort(key=lambda item: (-item["score"], item["name"].casefold(), item["id"]))
    return results[:limit]


def summarize_options(record: dict[str, Any]) -> dict[str, Any]:
    groups = record["option_groups"]
    return {
        "skill": record["name"],
        "source": record["skill_md"],
        "source_hash": record["source_hash"],
        "groups": groups,
        "group_counts": {
            category: sum(1 for group in groups if group["category"] == category)
            for category in sorted({group["category"] for group in groups})
        },
        "references": record["references"],
        "notice": "Extracted source facts only; explanations and rankings require navigation judgment.",
    }


def compare_records(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    return {
        "skills": [
            {
                "name": record["name"],
                "id": record["id"],
                "description": record["description"],
                "hosts": record["hosts"],
                "scopes": record["scopes"],
                "resources": record["resources"],
                "mentioned_formats": record["mentioned_formats"],
                "evidence_sections": record["evidence_sections"],
                "option_group_counts": summarize_options(record)["group_counts"],
                "parse_warnings": record["parse_warnings"],
            }
            for record in records
        ],
        "notice": "mentioned_formats are textual mentions, not proven outputs; compare source-established dimensions only.",
    }


def compact_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": record["name"],
        "id": record["id"],
        "description": record["description"],
        "hosts": record["hosts"],
        "scopes": record["scopes"],
        "resources": record["resources"],
        "option_group_counts": summarize_options(record)["group_counts"],
        "parse_warnings": record["parse_warnings"],
        "name_conflict": record["name_conflict"],
    }


def render_text(payload: Any) -> str:
    if isinstance(payload, dict) and "skills" in payload and isinstance(payload["skills"], list):
        lines = []
        for item in payload["skills"]:
            if isinstance(item, dict):
                lines.append(f"{item.get('name', '?')}: {item.get('description', '')}")
        if payload.get("warnings"):
            lines.append(f"Warnings: {len(payload['warnings'])}")
        return "\n".join(lines)
    return json.dumps(payload, ensure_ascii=False, indent=2)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", choices=("codex", "claude", "all"), default="all")
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    parser.add_argument("--root", action="append", type=Path, default=[])
    parser.add_argument("--include-self", action="store_true")
    parser.add_argument("--format", choices=("json", "text"), default="json")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("scan")
    list_parser = subparsers.add_parser("list")
    list_parser.add_argument("--limit", type=int, default=100)
    show_parser = subparsers.add_parser("show")
    show_parser.add_argument("skill")
    options_parser = subparsers.add_parser("options")
    options_parser.add_argument("skill")
    compare_parser = subparsers.add_parser("compare")
    compare_parser.add_argument("skills", nargs="+", help="two or more Skill names or canonical paths")
    search_parser = subparsers.add_parser("search")
    search_parser.add_argument("query", nargs="+")
    search_parser.add_argument("--limit", type=int, default=10)
    recommend_parser = subparsers.add_parser("recommend")
    recommend_parser.add_argument("task", nargs="+")
    recommend_parser.add_argument("--limit", type=int, default=10)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    cwd = expand(args.cwd).resolve(strict=False)
    inventory = scan_skills(cwd, args.host, args.root, args.include_self)
    try:
        if args.command == "scan":
            payload: Any = inventory
        elif args.command == "list":
            payload = {
                "schema_version": inventory["schema_version"],
                "host_filter": inventory["host_filter"],
                "skills": [compact_record(record) for record in inventory["skills"][: max(args.limit, 0)]],
                "total": len(inventory["skills"]),
                "conflicts": inventory["conflicts"],
                "warnings": inventory["warnings"],
            }
        elif args.command == "show":
            payload = select_skill(inventory, args.skill)
        elif args.command == "options":
            payload = summarize_options(select_skill(inventory, args.skill))
        elif args.command == "compare":
            if len(args.skills) < 2:
                raise ScanFailure("compare requires at least two Skills")
            payload = compare_records([select_skill(inventory, selector) for selector in args.skills])
        elif args.command == "search":
            query = " ".join(args.query)
            payload = {
                "query": query,
                "mode": "lexical-search",
                "results": search_records(inventory, query, args.limit),
                "notice": "Scores are lexical discovery aids, not semantic recommendations or official ratings.",
                "warnings": inventory["warnings"],
            }
        elif args.command == "recommend":
            query = " ".join(args.task)
            payload = {
                "query": query,
                "mode": "recommendation-candidate-seed",
                "results": search_records(inventory, query, args.limit),
                "candidate_universe": [
                    {
                        "name": record["name"],
                        "id": record["id"],
                        "description": record["description"],
                        "hosts": record["hosts"],
                        "section_titles": [section["title"] for section in record["sections"]],
                    }
                    for record in inventory["skills"]
                ],
                "notice": "Lexical scores are discovery aids only. Use candidate_universe for cross-language semantic judgment; neither is an official rating.",
                "warnings": inventory["warnings"],
            }
        else:
            parser.error(f"unsupported command: {args.command}")
            return 2
    except ScanFailure as exc:
        payload = {"error": str(exc), "warnings": inventory["warnings"]}
        output = render_text(payload) if args.format == "text" else json.dumps(payload, ensure_ascii=False, indent=2)
        print(output)
        return 2

    output = render_text(payload) if args.format == "text" else json.dumps(payload, ensure_ascii=False, indent=2)
    print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
