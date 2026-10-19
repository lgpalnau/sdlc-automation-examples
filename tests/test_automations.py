"""Tests for the SDLC automation examples."""

from __future__ import annotations

import subprocess
from typing import Any
from unittest.mock import patch

from automations import release_notes, telegram_to_issue
from automations.telegram_to_issue import IssueCommand


class TestReleaseNotes:
    def test_categorize_conventional_prefixes(self):
        assert release_notes.categorize("feat: add thing") == "Features"
        assert release_notes.categorize("fix(auth): repair login") == "Fixes"
        assert release_notes.categorize("docs: update readme") == "Docs"
        assert release_notes.categorize("chore(deps): bump lib") == "Chores"

    def test_categorize_unknown_goes_to_other(self):
        assert release_notes.categorize("refactor the widget") == "Other"

    def test_build_notes_groups_and_formats(self):
        entries = ["a1b2c3 feat: add search", "d4e5f6 fix: crash on empty input"]
        notes = release_notes.build_notes(entries, "v2.0.0")
        assert notes.startswith("# v2.0.0\n")
        assert "## Features" in notes
        assert "## Fixes" in notes
        assert "- feat: add search (a1b2c3)" in notes
        assert "- fix: crash on empty input (d4e5f6)" in notes

    def test_build_notes_skips_empty_sections(self):
        notes = release_notes.build_notes(["a1b2c3 fix: only a fix"], "t")
        assert "## Fixes" in notes
        assert "## Features" not in notes

    def test_build_notes_empty_input(self):
        assert release_notes.build_notes([], "t") == "# t\n"


class TestParseCommand:
    def test_issue_with_title_only(self):
        assert telegram_to_issue.parse_command("/issue deploy is broken") == (
            IssueCommand(title="deploy is broken", body="")
        )

    def test_issue_with_title_and_body(self):
        result = telegram_to_issue.parse_command(
            "/issue flaky test | fails on main only"
        )
        assert result == IssueCommand(title="flaky test", body="fails on main only")

    def test_command_is_case_insensitive(self):
        assert telegram_to_issue.parse_command("/ISSUE caps lock") is not None

    def test_command_addressed_to_bot(self):
        assert telegram_to_issue.parse_command("/issue@my_bot ci red | logs") == (
            IssueCommand(title="ci red", body="logs")
        )

    def test_non_command_returns_none(self):
        assert telegram_to_issue.parse_command("hello there") is None
        assert telegram_to_issue.parse_command("/help") is None
        assert telegram_to_issue.parse_command("/issues today") is None

    def test_bare_command_has_empty_title(self):
        for text in ("/issue", "/issue   ", "/issue@my_bot"):
            assert telegram_to_issue.parse_command(text) == IssueCommand("", "")


class TestCreateIssue:
    def test_runs_gh_and_returns_url(self):
        done = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="https://github.com/o/r/issues/7\n"
        )
        with patch.object(
            telegram_to_issue.subprocess, "run", return_value=done
        ) as run:
            url = telegram_to_issue.create_issue(repo="o/r", title="-v breaks", body="")
        assert url == "https://github.com/o/r/issues/7"
        # --flag=value keeps a title starting with "-" from being read as a flag.
        assert run.call_args.args[0] == [
            "gh",
            "issue",
            "create",
            "--repo",
            "o/r",
            "--title=-v breaks",
            "--body=",
        ]


def _update(text: str, *, user_id: int = 111, chat_id: int = -222, update_id: int = 1):
    return {
        "update_id": update_id,
        "message": {
            "message_id": 9,
            "from": {"id": user_id},
            "chat": {"id": chat_id},
            "text": text,
        },
    }


class TestHandleUpdate:
    def test_allowed_user_creates_issue_and_gets_reply(self):
        with (
            patch.object(
                telegram_to_issue, "create_issue", return_value="https://x/1"
            ) as create,
            patch.object(telegram_to_issue, "telegram") as tg,
        ):
            url = telegram_to_issue.handle_update(
                _update("/issue ship it | friday"),
                repo="o/r",
                allowed={111},
                token="tok",
            )
        assert url == "https://x/1"
        create.assert_called_once_with(repo="o/r", title="ship it", body="friday")
        tg.assert_called_once_with(
            "tok",
            "sendMessage",
            chat_id=-222,
            text="Created https://x/1",
            reply_to_message_id=9,
        )

    def test_allowlist_matches_user_not_chat(self):
        # A stranger posting in an allowlisted group chat is still rejected.
        with (
            patch.object(telegram_to_issue, "create_issue") as create,
            patch.object(telegram_to_issue, "telegram") as tg,
        ):
            url = telegram_to_issue.handle_update(
                _update("/issue spam", user_id=333),
                repo="o/r",
                allowed={-222},
                token="tok",
            )
        assert url is None
        create.assert_not_called()
        tg.assert_not_called()

    def test_non_command_is_ignored(self):
        with (
            patch.object(telegram_to_issue, "create_issue") as create,
            patch.object(telegram_to_issue, "telegram") as tg,
        ):
            for update in (_update("just chatting"), {"update_id": 2}):
                assert (
                    telegram_to_issue.handle_update(
                        update, repo="o/r", allowed={111}, token="tok"
                    )
                    is None
                )
        create.assert_not_called()
        tg.assert_not_called()

    def test_bare_command_replies_with_usage(self):
        with (
            patch.object(telegram_to_issue, "create_issue") as create,
            patch.object(telegram_to_issue, "telegram") as tg,
        ):
            url = telegram_to_issue.handle_update(
                _update("/issue"), repo="o/r", allowed={111}, token="tok"
            )
        assert url is None
        create.assert_not_called()
        assert tg.call_args.kwargs["text"] == "Usage: /issue <title> [| <body>]"

    def test_gh_failure_is_reported_in_chat(self):
        error = subprocess.CalledProcessError(1, ["gh"], stderr="HTTP 404: Not Found\n")
        with (
            patch.object(telegram_to_issue, "create_issue", side_effect=error),
            patch.object(telegram_to_issue, "telegram") as tg,
        ):
            url = telegram_to_issue.handle_update(
                _update("/issue t"), repo="o/r", allowed={111}, token="tok"
            )
        assert url is None
        assert (
            tg.call_args.kwargs["text"] == "Failed to create issue: HTTP 404: Not Found"
        )


class TestPoll:
    def test_handles_batch_and_advances_offset(self, capsys):
        updates = [_update("/issue a", update_id=41), _update("/issue b", update_id=42)]

        def fake_telegram(token: str, method: str, **params: Any) -> Any:
            return updates if method == "getUpdates" else {}

        def fake_create(*, repo: str, title: str, body: str) -> str:
            if title == "a":
                raise FileNotFoundError("gh")
            return f"https://x/{title}"

        with (
            patch.object(telegram_to_issue, "telegram", fake_telegram),
            patch.object(telegram_to_issue, "create_issue", fake_create),
        ):
            offset = telegram_to_issue.poll("tok", 0, repo="o/r", allowed={111})
        assert offset == 43
        assert "created: https://x/b" in capsys.readouterr().out


def test_main_requires_bot_token(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    assert telegram_to_issue.main(["--repo", "o/r", "--allow", "1"]) == 2
