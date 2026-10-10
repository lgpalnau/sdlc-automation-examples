"""Turn a chat message into a GitHub issue.

The encrypted-chat trigger pattern, popular with agentic harnesses: a chat
message becomes a tracked work item without opening a browser.

Wiring (Signal): pipe signal-cli's JSON output into this script::

    signal-cli -u +15551234567 receive --json | \\
        uv run automations/signal_to_issue.py --repo owner/repo

Any message starting with ``/issue`` becomes a GitHub issue. Requires the
``GITHUB_TOKEN`` environment variable. The parsing and issue-creation logic
is transport-agnostic — swap the stdin loop for a webhook handler and the
rest stays the same.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass
class IssueCommand:
    title: str
    body: str


def parse_command(text: str) -> IssueCommand | None:
    """Parse ``/issue <title> [| <body>]``. Returns None when not a command."""
    stripped = text.strip()
    if not stripped.lower().startswith("/issue"):
        return None
    rest = stripped[len("/issue") :].strip()
    if not rest:
        return None
    title, sep, body = rest.partition("|")
    return IssueCommand(title=title.strip(), body=body.strip() if sep else "")


def extract_text(envelope: dict[str, Any]) -> str | None:
    """Pull the message text out of a signal-cli JSON envelope."""
    try:
        message = envelope["envelope"]["dataMessage"]["message"]
    except (KeyError, TypeError):
        return None
    return message if isinstance(message, str) else None


def create_issue(*, repo: str, title: str, body: str, token: str) -> str:
    """Create a GitHub issue via the REST API. Returns the issue URL."""
    payload = json.dumps({"title": title, "body": body}).encode()
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/issues",
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "sdlc-automation-examples",
        },
    )
    with urllib.request.urlopen(request) as response:
        data = json.load(response)
    url = data.get("html_url")
    if not isinstance(url, str):
        raise TypeError(f"unexpected GitHub response: {data!r}")
    return url


def handle_envelope(envelope: dict[str, Any], *, repo: str, token: str) -> str | None:
    """Process one signal-cli envelope. Returns the issue URL, or None."""
    text = extract_text(envelope)
    if not text:
        return None
    command = parse_command(text)
    if command is None:
        return None
    return create_issue(
        repo=repo, title=command.title, body=command.body, token=token
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create GitHub issues from chat messages on stdin."
    )
    parser.add_argument(
        "--repo", required=True, help="owner/repo to file issues in"
    )
    args = parser.parse_args(argv)

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("error: GITHUB_TOKEN is not set", file=sys.stderr)
        return 2

    created = 0
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            envelope = json.loads(line)
        except json.JSONDecodeError as exc:
            print(f"warn: skipping bad JSON line: {exc}", file=sys.stderr)
            continue
        if not isinstance(envelope, dict):
            print("warn: skipping non-object JSON line", file=sys.stderr)
            continue
        try:
            url = handle_envelope(envelope, repo=args.repo, token=token)
        except Exception as exc:  # noqa: BLE001 — one bad message must not kill the poll loop
            print(f"error: {exc}", file=sys.stderr)
            continue
        if url:
            print(f"created: {url}")
            created += 1
    print(f"done: {created} issue(s) created")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
