#!/usr/bin/env python3
"""Lint SKILL.md and plugin.json.

Rules:
1. plugin.json parses as JSON and has {name, version, description}.
2. Every skills/<dir>/SKILL.md exists, has YAML frontmatter that parses,
   and includes `name` and `description`.
3. The `name` field matches the directory name.
4. If any skill file was added or modified in this diff, plugin.json's version
   must have been bumped vs the base ref. (Only enforced when BASE_REF is set.)

Exit non-zero on any failure. Prints every finding first.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)
findings: list[str] = []


def fail(msg: str) -> None:
    findings.append(f"::error::{msg}")


def parse_frontmatter(text: str) -> dict[str, str] | None:
    m = FRONTMATTER_RE.match(text)
    if not m:
        return None
    body = m.group(1)
    out: dict[str, str] = {}
    key: str | None = None
    for line in body.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith((" ", "\t")) and key is not None:
            out[key] += " " + line.strip()
            continue
        if ":" not in line:
            return None
        k, _, v = line.partition(":")
        key = k.strip()
        out[key] = v.strip().strip('"').strip("'")
    return out


def check_plugin_json() -> dict | None:
    p = REPO / ".claude-plugin" / "plugin.json"
    if not p.exists():
        fail(f"{p.relative_to(REPO)}: missing")
        return None
    try:
        data = json.loads(p.read_text())
    except json.JSONDecodeError as e:
        fail(f"{p.relative_to(REPO)}: not valid JSON — {e}")
        return None
    for field in ("name", "version", "description"):
        if field not in data:
            fail(f"{p.relative_to(REPO)}: missing required field '{field}'")
    return data


def check_skills() -> None:
    skills_root = REPO / "skills"
    if not skills_root.exists():
        return
    for skill_dir in sorted(skills_root.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_md = skill_dir / "SKILL.md"
        rel = skill_md.relative_to(REPO)
        if not skill_md.exists():
            fail(f"{rel}: missing")
            continue
        fm = parse_frontmatter(skill_md.read_text())
        if fm is None:
            fail(f"{rel}: frontmatter did not parse (need `---` … `---` block with `key: value` lines)")
            continue
        for field in ("name", "description"):
            if field not in fm or not fm[field]:
                fail(f"{rel}: missing required frontmatter field '{field}'")
        if fm.get("name") and fm["name"] != skill_dir.name:
            fail(f"{rel}: `name: {fm['name']}` does not match directory `{skill_dir.name}`")


def check_version_bumped() -> None:
    base = os.environ.get("BASE_REF")
    if not base:
        return
    try:
        diff = subprocess.run(
            ["git", "diff", "--name-only", f"origin/{base}...HEAD"],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.splitlines()
    except subprocess.CalledProcessError as e:
        fail(f"git diff against origin/{base} failed: {e.stderr.strip()}")
        return
    skill_changes = [f for f in diff if f.startswith("skills/") or f.startswith("agents/") or f.startswith("hooks/")]
    if not skill_changes:
        return
    try:
        old_plugin = subprocess.run(
            ["git", "show", f"origin/{base}:.claude-plugin/plugin.json"],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except subprocess.CalledProcessError:
        return
    try:
        old = json.loads(old_plugin)
        new = json.loads((REPO / ".claude-plugin" / "plugin.json").read_text())
    except json.JSONDecodeError:
        return
    if old.get("version") == new.get("version"):
        fail(
            f"plugin.json version {new.get('version')!r} unchanged from origin/{base}, "
            f"but skills/agents/hooks were modified: {', '.join(skill_changes[:5])}"
            + ("…" if len(skill_changes) > 5 else "")
        )


def main() -> int:
    check_plugin_json()
    check_skills()
    check_version_bumped()
    for f in findings:
        print(f)
    if findings:
        print(f"\nFAIL: {len(findings)} issue(s)")
        return 1
    print("OK: skills and plugin.json pass lint")
    return 0


if __name__ == "__main__":
    sys.exit(main())
