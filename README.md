# SDLC Automation Examples

Small, real-world Python automation scripts for the software delivery
lifecycle — the kind of weekend-sized work I do for small teams.
Managed with [uv](https://docs.astral.sh/uv/), formatted and linted with
[ruff](https://docs.astral.sh/ruff/), type-checked with
[ty](https://github.com/bwhmather/ty), unit tested with [pytest](https://docs.pytest.org/en/stable/), and gated by
GitHub Actions on every commit pushed.

## Examples

| Example | What it does |
| --- | --- |
| `automations/release_notes.py` | Generates Markdown release notes from `git log` between two refs, grouped by conventional-commit category |
| `automations/signal_to_issue.py` | Chat-triggered automation: messages starting with `/issue` (e.g. from Signal via `signal-cli`) become GitHub issues through the REST API |
| `justfile` | Standardized commands: `up`, `down`, `fmt`, `lint`, `ty`, `test`, `clean`, `run-workflow`, `run-release-notes`, `run-signal-to-issue` |

## Quickstart

```bash
just up                 # uv sync — create the environment and install dev deps
just test               # format, lint, type-check, and test modified files
just test all           # full format, lint, type-check, and entire test suite
just clean              # remove generated artifacts
just down               # remove the environment
```

Or without [just](https://just.systems/):

```bash
uv sync
uv run ruff format .
uv run ruff check --fix .
uvx ty check .
uv run pytest
```

## Running the Examples & Workflows

### Triggering GitHub Actions via GitHub CLI

Dispatch GitHub Actions workflows directly from the terminal using `gh`:

```bash
# View available flags and help
just run-workflow

# Trigger a workflow by file name or workflow ID
just run-workflow release.yml -f version=v1.2.0
```

### Release Notes Generator

```bash
# Show options
just run-release-notes --help

# Generate release notes since the last tag
just run-release-notes --since v1.2.0 --title "v1.3.0"
```

### Signal to GitHub Issue

```bash
export GITHUB_TOKEN=ghp_...

# View arguments
just run-signal-to-issue --help

# Run listener pipe from signal-cli JSON envelopes
signal-cli -u +15551234567 receive --json | \
    just run-signal-to-issue --repo owner/repo
# then send "/issue deploy is broken | fails on staging" from Signal
```

The issue-creation logic is transport-agnostic: the stdin loop can be
swapped for a webhook handler and the parsing + GitHub API code stays
the same.

## Optional integrations

`examples-optional/` shows how these scripts plug into services you may
already use. Nothing here is required.

- **Swamp ([swamp-club.com](https://swamp-club.com))** — AI-built
  automation platform: an agent authors a validated, versioned model
  that runs the same way every time, with every run recorded.
  `examples-optional/swamp/release-notes-model.yaml` wraps the
  release-notes script as a `command/shell` model (following Swamp's
  documented model format), and
  `examples-optional/swamp/nightly-release-notes-workflow.yaml`
  chains it into a workflow you can trigger on demand, on a schedule,
  or from a webhook. Validate with `swamp model validate` — the YAML
  here follows their published schema but I haven't run their CLI
  against it.
- **exe.dev ([exe.dev](https://exe.dev))** — durable, private VMs for
  developers and agents (you're root, with systemd). A natural
  always-on host for the chat listener:
  `examples-optional/exe-dev/signal-poller.service` is a systemd unit
  that keeps `signal_to_issue.py` polling Signal 24/7, restarting on
  failure. Edit the number/repo, drop your `GITHUB_TOKEN` in
  `/etc/signal-poller.env`, `systemctl enable --now signal-poller`.

## Why this exists

Portfolio proof for my SDLC automation services
(Contra / Fiverr): Python automation + GitHub Actions CI setup for
small teams. Starter tier: repo audit, one automation script like
these, CI workflow with README. Standard tier adds acceptance tests,
branch protection, and status badges.
