"""Turn a Telegram message into a GitHub issue.

The chat-trigger pattern, popular with agentic harnesses: a chat message
becomes a tracked work item without opening a browser.

The script long-polls the Telegram Bot API. A message starting with
``/issue`` from an allowlisted Telegram user becomes a GitHub issue, created
with ``gh issue create``, so authentication is whatever ``gh auth`` already
has. The bot replies in the chat with the new issue's URL::

    export TELEGRAM_BOT_TOKEN=123456:ABC...   # from @BotFather
    gh auth login
    uv run automations/telegram_to_issue.py --repo owner/repo --allow 123456789

Message format: ``/issue <title> [| <body>]``.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

POLL_SECONDS = 30


@dataclass
class IssueCommand:
    title: str
    body: str


def parse_command(text: str) -> IssueCommand | None:
    """Parse ``/issue[@bot] <title> [| <body>]``. Returns None when not a command.

    A bare ``/issue`` (what Telegram's command menu sends) gives an empty title.
    """
    parts = text.split(maxsplit=1)
    if not parts or parts[0].lower().partition("@")[0] != "/issue":
        return None
    title, sep, body = (parts[1] if len(parts) > 1 else "").partition("|")
    return IssueCommand(title=title.strip(), body=body.strip() if sep else "")


def telegram(token: str, method: str, **params: Any) -> Any:
    """Call a Telegram Bot API method and return its ``result``."""
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/{method}",
        data=json.dumps(params).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=POLL_SECONDS + 10) as response:
        return json.load(response)["result"]


def create_issue(*, repo: str, title: str, body: str) -> str:
    """Create a GitHub issue with the gh CLI. Returns the issue URL."""
    result = subprocess.run(
        ["gh", "issue", "create", "--repo", repo, f"--title={title}", f"--body={body}"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def handle_update(
    update: dict[str, Any], *, repo: str, allowed: set[int], token: str
) -> str | None:
    """Process one Telegram update. Returns the new issue URL, or None."""
    message = update.get("message") or {}
    text = message.get("text")
    user_id = message.get("from", {}).get("id")
    command = parse_command(text) if isinstance(text, str) else None
    if command is None:
        print(f"info: ignoring non-/issue message from user {user_id}", file=sys.stderr)
        return None
    if user_id not in allowed:
        print(f"warn: ignoring /issue from user {user_id}", file=sys.stderr)
        return None
    url = None
    if not command.title:
        reply = "Usage: /issue <title> [| <body>"
    else:
        try:
            url = create_issue(repo=repo, title=command.title, body=command.body)
            reply = f"Created {url}"
        except subprocess.CalledProcessError as exc:
            reply = f"Failed to create issue: {exc.stderr.strip()}"
            print(f"error: {exc}", file=sys.stderr)
    telegram(
        token,
        "sendMessage",
        chat_id=message["chat"]["id"],
        text=reply,
        reply_to_message_id=message["message_id"],
    )
    return url


def poll(token: str, offset: int, *, repo: str, allowed: set[int]) -> int:
    """Fetch and handle one batch of updates. Returns the next offset."""
    updates = telegram(
        token,
        "getUpdates",
        offset=offset,
        timeout=POLL_SECONDS,
        allowed_updates=["message"],
    )
    for update in updates:
        offset = update["update_id"] + 1
        try:
            url = handle_update(update, repo=repo, allowed=allowed, token=token)
        except Exception as exc:  # noqa: BLE001 — one bad message must not kill the poll loop
            print(f"error: {exc}", file=sys.stderr)
            continue
        if url:
            print(f"created: {url}")
    return offset


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create GitHub issues from Telegram /issue messages."
    )
    parser.add_argument("--repo", required=True, help="owner/repo to file issues in")
    parser.add_argument(
        "--allow",
        type=int,
        action="append",
        required=True,
        metavar="USER_ID",
        help="numeric Telegram user ID allowed to file issues (repeatable)",
    )
    args = parser.parse_args(argv)

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("error: TELEGRAM_BOT_TOKEN is not set", file=sys.stderr)
        return 2

    bot = telegram(token, "getMe")
    print(f"@{bot['username']} filing issues in {args.repo}", file=sys.stderr)
    offset = 0
    while True:
        try:
            offset = poll(token, offset, repo=args.repo, allowed=set(args.allow))
        except (urllib.error.URLError, TimeoutError) as exc:
            print(f"warn: polling failed, retrying: {exc}", file=sys.stderr)
            time.sleep(5)


if __name__ == "__main__":
    raise SystemExit(main())
