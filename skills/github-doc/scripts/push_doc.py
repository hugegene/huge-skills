#!/usr/bin/env python3
"""Publish a Markdown document and README link; adapted from Lily's guarded CLI."""

from __future__ import annotations

import argparse
import difflib
import posixpath
import re
from pathlib import Path
from urllib.parse import quote

import api


def doc_title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        match = re.match(r"^#\s+(.+?)\s*#*\s*$", line)
        if match:
            return match.group(1).strip()
    return fallback


def insert_readme_link(readme: str, path: str, link_text: str,
                       section: str | None) -> tuple[str, bool]:
    """Insert one link, preserving existing section content and nested headings."""
    if re.search(r"\]\(\s*" + re.escape(path) + r"\s*\)", readme):
        return readme, False
    label = link_text.replace("\\", "\\\\").replace("[", r"\[").replace("]", r"\]")
    bullet = f"- [{label}]({path})"
    lines = readme.splitlines()
    if section:
        heading = re.match(r"^(#{1,6})\s+\S", section)
        if not heading:
            raise ValueError('--readme-section must be a Markdown heading such as "## Notes"')
        level = len(heading.group(1))
        start = next((i for i, line in enumerate(lines) if line.strip() == section), None)
        if start is not None:
            end = len(lines)
            for i in range(start + 1, len(lines)):
                next_heading = re.match(r"^(#{1,6})\s+", lines[i])
                if next_heading and len(next_heading.group(1)) <= level:
                    end = i
                    break
            # Append after section content, ahead of trailing blank lines.
            while end > start + 1 and not lines[end - 1].strip():
                end -= 1
            insertion = [] if end == start + 1 or lines[end - 1].startswith(("- ", "* ")) else [""]
            if end == start + 1:
                insertion.append("")
            insertion.append(bullet)
            if end < len(lines) and lines[end].strip():
                insertion.append("")
            lines[end:end] = insertion
            return "\n".join(lines) + "\n", True
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend([section, "", bullet])
    else:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(bullet)
    return "\n".join(lines) + "\n", True


def _diff(old: str, new: str, path: str) -> str:
    return "".join(difflib.unified_diff(
        old.splitlines(keepends=True), new.splitlines(keepends=True),
        fromfile=f"a/{path}", tofile=f"b/{path}", n=3))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Preview a Markdown document + README link; commit with --push.")
    parser.add_argument("file", type=Path, help="local UTF-8 Markdown file")
    parser.add_argument("--repo", required=True, help="destination owner/repo")
    parser.add_argument("--path", help="destination path (default: local filename)")
    parser.add_argument("--branch", help="destination branch (default: repository default branch)")
    parser.add_argument("--readme-path", default="README.md")
    parser.add_argument("--readme-section", help='heading such as "## Notes"')
    parser.add_argument("--link-text", help="default: first H1, otherwise filename")
    parser.add_argument("--message", help="document commit message")
    parser.add_argument("--no-readme", action="store_true")
    parser.add_argument("--push", action="store_true", help="create commits (default is read-only preview)")
    args = parser.parse_args(argv)

    if not re.fullmatch(r"[A-Za-z0-9-]+/[A-Za-z0-9_.-]+", args.repo):
        parser.error("--repo must be owner/repo")
    owner, repo = args.repo.split("/")
    target = args.path or args.file.name
    api.validate_path(target)
    api.validate_path(args.readme_path)
    if not args.no_readme and target == args.readme_path:
        parser.error("document and README paths must differ (or use --no-readme)")
    if args.readme_section and not re.match(r"^#{1,6}\s+\S", args.readme_section.strip()):
        parser.error("--readme-section must be a Markdown heading")
    content = args.file.read_text(encoding="utf-8")
    message = args.message if args.message is not None else f"docs: update {target}"
    if not message.strip():
        parser.error("--message must be non-empty")
    link_text = args.link_text or doc_title(content, Path(target).stem)
    if "\n" in link_text or "\r" in link_text:
        parser.error("--link-text must be a single line")
    info = api.get_repo(owner, repo)
    branch = args.branch or info["default_branch"]
    existing = api.get_file(owner, repo, target, branch)
    # Entries retain the SHA from planning, so a later update cannot clobber a concurrent edit.
    changes = []
    if existing["content"] != content:
        changes.append((target, existing, content, message))
    if not args.no_readme:
        readme = api.get_file(owner, repo, args.readme_path, branch)
        link_path = quote(posixpath.relpath(target, posixpath.dirname(args.readme_path) or "."), safe="/.-_")
        new_readme, changed = insert_readme_link(
            readme["content"] or "", link_path, link_text,
            args.readme_section.strip() if args.readme_section else None)
        if changed:
            changes.append((args.readme_path, readme, new_readme, f"docs: link {target} in {args.readme_path}"))

    print(f"repo: {args.repo}@{branch}")
    for path, old, new, commit_message in changes:
        print(f"\n{'update' if old['exists'] else 'create'}: {path}; message={commit_message!r}")
        print(_diff(old["content"] or "", new, path))
    if not changes:
        print("No changes; document and requested link are already present.")
        return
    if not args.push:
        print(f"Preview only: {len(changes)} commit(s) planned. Re-run with --push when authorized.")
        return

    completed = []
    try:
        for path, old, new, commit_message in changes:
            result = api.put_file(owner, repo, path, new, commit_message, branch, old["sha"])
            completed.append(path)
            print(f"Committed {path}: {result.get('commit', {}).get('html_url', '(URL unavailable)')}")
    except ValueError as exc:
        if completed:
            raise ValueError(
                f"Partial success: committed {', '.join(completed)}; failed at {path}. "
                f"{exc} Inspect the branch and preview again; unchanged files will be skipped."
            ) from None
        raise


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as exc:
        raise SystemExit(f"Error: {exc}") from None
