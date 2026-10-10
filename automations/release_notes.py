"""Generate Markdown release notes from git history between two refs."""
from __future__ import annotations

import argparse
import subprocess
import sys

CATEGORIES = (
    ("feat", "Features"),
    ("fix", "Fixes"),
    ("docs", "Docs"),
    ("chore", "Chores"),
)


def git_log(since_ref: str, until_ref: str = "HEAD") -> list[str]:
    """Return raw 'sha subject' lines for commits in since_ref..until_ref."""
    cmd = ["git", "log", f"{since_ref}..{until_ref}", "--pretty=format:%h %s"]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"git log failed: {result.stderr.strip()}")
    return [line for line in result.stdout.splitlines() if line.strip()]


def categorize(subject: str) -> str:
    """Map a commit subject to a release-notes section."""
    prefix = subject.split(":")[0].lower().strip()
    for key, label in CATEGORIES:
        if prefix.startswith(key):
            return label
    return "Other"


def build_notes(entries: list[str], title: str) -> str:
    """Group 'sha subject' entries into a Markdown document."""
    groups: dict[str, list[str]] = {}
    for entry in entries:
        sha, _, subject = entry.partition(" ")
        groups.setdefault(categorize(subject), []).append(f"- {subject} ({sha})")
    lines = [f"# {title}", ""]
    for _, label in (*CATEGORIES, ("", "Other")):
        items = groups.get(label)
        if items:
            lines += [f"## {label}", *items, ""]
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate release notes from git log."
    )
    parser.add_argument("--since", required=True, help="Ref to start from, e.g. v1.2.0")
    parser.add_argument("--until", default="HEAD")
    parser.add_argument("--title", default="Release notes")
    parser.add_argument("--output", help="Write to a file instead of stdout")
    args = parser.parse_args(argv)

    notes = build_notes(git_log(args.since, args.until), args.title)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(notes)
    else:
        sys.stdout.write(notes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
