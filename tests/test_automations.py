"""Tests for the SDLC automation examples."""
from __future__ import annotations

import io
import json
from typing import Any
from unittest.mock import patch

from automations import release_notes, signal_to_issue
from automations.signal_to_issue import IssueCommand


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
        assert signal_to_issue.parse_command("/issue deploy is broken") == (
            IssueCommand(title="deploy is broken", body="")
        )

    def test_issue_with_title_and_body(self):
        result = signal_to_issue.parse_command("/issue flaky test | fails on main only")
        assert result == IssueCommand(title="flaky test", body="fails on main only")

    def test_command_is_case_insensitive(self):
        assert signal_to_issue.parse_command("/ISSUE caps lock") is not None

    def test_non_command_returns_none(self):
        assert signal_to_issue.parse_command("hello there") is None
        assert signal_to_issue.parse_command("/help") is None

    def test_bare_command_returns_none(self):
        assert signal_to_issue.parse_command("/issue") is None
        assert signal_to_issue.parse_command("/issue   ") is None


class TestExtractText:
    def test_pulls_message_from_envelope(self):
        envelope = {"envelope": {"dataMessage": {"message": "/issue hi"}}}
        assert signal_to_issue.extract_text(envelope) == "/issue hi"

    def test_missing_keys_return_none(self):
        assert signal_to_issue.extract_text({}) is None
        assert signal_to_issue.extract_text({"envelope": {}}) is None
        assert signal_to_issue.extract_text({"envelope": {"dataMessage": {}}}) is None

    def test_non_string_message_returns_none(self):
        envelope = {"envelope": {"dataMessage": {"message": 42}}}
        assert signal_to_issue.extract_text(envelope) is None


class FakeResponse:
    def __init__(self, payload: dict[str, Any]):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self._payload).encode()


class TestCreateIssue:
    def test_posts_to_github_api(self):
        seen: dict[str, Any] = {}

        def fake_urlopen(request: Any) -> FakeResponse:
            seen["url"] = request.full_url
            seen["method"] = request.get_method()
            seen["auth"] = request.get_header("Authorization")
            seen["payload"] = json.loads(request.data.decode())
            return FakeResponse({"html_url": "https://github.com/o/r/issues/7"})

        with patch.object(
            signal_to_issue.urllib.request, "urlopen", fake_urlopen
        ):
            url = signal_to_issue.create_issue(
                repo="o/r", title="t", body="b", token="tok"
            )
        assert url == "https://github.com/o/r/issues/7"
        assert seen["url"] == "https://api.github.com/repos/o/r/issues"
        assert seen["method"] == "POST"
        assert seen["auth"] == "Bearer tok"
        assert seen["payload"] == {"title": "t", "body": "b"}

    def test_unexpected_response_raises(self):
        with patch.object(
            signal_to_issue.urllib.request,
            "urlopen",
            lambda req: FakeResponse({"nope": True}),
        ):
            try:
                signal_to_issue.create_issue(
                    repo="o/r", title="t", body="", token="tok"
                )
            except TypeError:
                pass
            else:
                raise AssertionError("expected TypeError")


class TestHandleEnvelope:
    def _envelope(self, text: str) -> dict[str, Any]:
        return {"envelope": {"dataMessage": {"message": text}}}

    def test_command_creates_issue(self):
        with patch.object(
            signal_to_issue, "create_issue", return_value="https://x/1"
        ) as mock:
            url = signal_to_issue.handle_envelope(
                self._envelope("/issue ship it | friday"),
                repo="o/r",
                token="tok",
            )
        assert url == "https://x/1"
        mock.assert_called_once_with(
            repo="o/r", title="ship it", body="friday", token="tok"
        )

    def test_non_command_envelope_returns_none(self):
        with patch.object(signal_to_issue, "create_issue") as mock:
            assert signal_to_issue.handle_envelope(
                self._envelope("just chatting"), repo="o/r", token="tok"
            ) is None
            mock.assert_not_called()

    def test_main_reads_stdin_and_reports(self, monkeypatch, capsys):
        monkeypatch.setenv("GITHUB_TOKEN", "tok")
        line = json.dumps(self._envelope("/issue from stdin"))
        monkeypatch.setattr("sys.stdin", io.StringIO(line + "\n"))
        with patch.object(
            signal_to_issue, "create_issue", return_value="https://x/2"
        ):
            rc = signal_to_issue.main(["--repo", "o/r"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "created: https://x/2" in out
        assert "done: 1 issue(s) created" in out

    def test_main_requires_token(self, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        rc = signal_to_issue.main(["--repo", "o/r"])
        assert rc == 2
