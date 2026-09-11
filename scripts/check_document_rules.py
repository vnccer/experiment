"""Read-only checks for the campus-security documentation rules."""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import unquote


ROOT_DOCS = {
    "README.md",
    "思路.md",
    "思路_关键图解.md",
    "每次codex执行前必读prompt.md",
}
CURRENT_STATUS = "每次codex执行前必读prompt.md"
LINE_LIMITS = {"README.md": 60, CURRENT_STATUS: 100}
TRANSCRIPT_HEADING = re.compile(
    r"^##\s+.*(?:模型.*原文|原始模型回答|原文与记录).*?$", re.MULTILINE
)
STALE_DIRECTIVES = (
    re.compile(r"^#{1,6}\s*下一步\s*$", re.MULTILINE),
    re.compile(r"^#{1,6}\s*下一小阶段", re.MULTILINE),
    re.compile(r"请现在只推进"),
    re.compile(r"请现在只做"),
)
LOCAL_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def line_count(path: Path) -> int:
    return len(read_text(path).splitlines())


def maintained_markdown(root: Path) -> list[Path]:
    paths: set[Path] = set(root.glob("*.md"))
    for relative in (
        "history",
        "prompts",
        "templates",
        "dataset/campus_security_adapted",
        "agentdojo-0.1.35/examples/campus_security",
        "agentdojo-0.1.35/runs/campus_security",
    ):
        directory = root / relative
        if directory.exists():
            paths.update(directory.rglob("*.md"))
    return sorted(paths)


def is_history(path: Path, root: Path) -> bool:
    relative = path.relative_to(root)
    return "history" in relative.parts


def check_root_docs(root: Path, errors: list[str]) -> None:
    actual = {path.name for path in root.glob("*.md")}
    missing = ROOT_DOCS - actual
    extra = actual - ROOT_DOCS
    if missing:
        errors.append(f"根目录缺少必需文档：{sorted(missing)}")
    if extra:
        errors.append(f"根目录存在未授权 Markdown：{sorted(extra)}")


def check_line_limits(root: Path, errors: list[str]) -> None:
    for name, limit in LINE_LIMITS.items():
        path = root / name
        if path.exists() and (count := line_count(path)) > limit:
            errors.append(f"{name} 共{count}行，超过{limit}行上限")

    results_root = root / "agentdojo-0.1.35/runs/campus_security"
    if results_root.exists():
        for path in results_root.rglob("RESULTS.md"):
            count = line_count(path)
            if count > 120:
                errors.append(
                    f"{path.relative_to(root)} 共{count}行，超过运行报告120行上限"
                )


def check_history_markers(root: Path, errors: list[str]) -> None:
    for path in maintained_markdown(root):
        if not is_history(path, root):
            continue
        opening = "\n".join(read_text(path).splitlines()[:8])
        if not re.search(r"历史归档|已停用|已于.{0,20}停用|旧会话交接记录", opening):
            errors.append(f"历史文档缺少首屏归档标记：{path.relative_to(root)}")


def check_stale_directives(root: Path, errors: list[str]) -> None:
    allowed = root / CURRENT_STATUS
    for path in maintained_markdown(root):
        if path == allowed or is_history(path, root):
            continue
        text = read_text(path)
        for pattern in STALE_DIRECTIVES:
            if pattern.search(text):
                errors.append(
                    f"非当前状态文档含执行指令：{path.relative_to(root)} / {pattern.pattern}"
                )


def check_result_transcripts(root: Path, errors: list[str]) -> None:
    results_root = root / "agentdojo-0.1.35/runs/campus_security"
    if not results_root.exists():
        return
    for path in results_root.rglob("RESULTS.md"):
        text = read_text(path)
        headings = list(TRANSCRIPT_HEADING.finditer(text))
        for match in headings:
            section_start = match.end()
            next_heading = re.search(r"^##\s+", text[section_start:], re.MULTILINE)
            section_end = (
                section_start + next_heading.start() if next_heading else len(text)
            )
            body_lines = [
                line for line in text[section_start:section_end].splitlines() if line.strip()
            ]
            if len(body_lines) > 10:
                errors.append(
                    f"运行报告的模型原文章节超过10行：{path.relative_to(root)} / "
                    f"{match.group(0)}"
                )


def check_local_links(root: Path, errors: list[str]) -> None:
    for path in maintained_markdown(root):
        for raw_target in LOCAL_LINK.findall(read_text(path)):
            target = raw_target.strip().strip("<>").split("#", 1)[0]
            if not target or re.match(r"^[a-z][a-z0-9+.-]*://", target, re.I):
                continue
            resolved = (path.parent / unquote(target)).resolve()
            if not resolved.exists():
                errors.append(
                    f"本地链接失效：{path.relative_to(root)} -> {raw_target}"
                )


def prose_paragraphs(path: Path) -> set[str]:
    paragraphs: set[str] = set()
    in_fence = False
    current: list[str] = []

    def flush() -> None:
        if not current:
            return
        paragraph = " ".join(current)
        normalized = re.sub(r"\s+", "", paragraph)
        if len(normalized) >= 120:
            paragraphs.add(normalized)
        current.clear()

    for line in read_text(path).splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            flush()
            in_fence = not in_fence
            continue
        if in_fence or not stripped:
            flush()
            continue
        if stripped.startswith(("#", "|", "- ", ">", "1. ", "2. ", "3. ")):
            flush()
            continue
        current.append(stripped)
    flush()
    return paragraphs


def check_duplicate_paragraphs(root: Path, errors: list[str]) -> None:
    owners: dict[str, list[Path]] = defaultdict(list)
    for path in maintained_markdown(root):
        if is_history(path, root) or path.name == "思路.md":
            continue
        for paragraph in prose_paragraphs(path):
            owners[paragraph].append(path)
    for paths in owners.values():
        unique = sorted(set(paths))
        if len(unique) > 1:
            locations = ", ".join(str(path.relative_to(root)) for path in unique)
            errors.append(f"多个活跃文档包含相同长段落：{locations}")


def check_protected_paths(root: Path, errors: list[str]) -> None:
    protected = (root / "思路.md", root / "2026年度教育网络安全专项研究课题")
    for path in protected:
        if not path.exists():
            errors.append(f"受保护路径不存在：{path.relative_to(root)}")


def run(root: Path) -> list[str]:
    errors: list[str] = []
    check_root_docs(root, errors)
    check_line_limits(root, errors)
    check_history_markers(root, errors)
    check_stale_directives(root, errors)
    check_result_transcripts(root, errors)
    check_local_links(root, errors)
    check_duplicate_paragraphs(root, errors)
    check_protected_paths(root, errors)
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="实验根目录，默认取本脚本上一级目录",
    )
    args = parser.parse_args()
    root = args.root.resolve()
    errors = run(root)

    if errors:
        print(f"文档约束检查失败：{len(errors)}项")
        for error in errors:
            print(f"- {error}")
        print("检查器只报告问题，不会修改文件。")
        return 1

    print("文档约束检查通过。")
    print("检查器未修改任何文件。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
