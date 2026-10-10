# Repo command standards.
set dotenv-load

# Bring the dev environment up
up:
    uv sync

# Tear the dev environment down
down:
    rm -rf .venv

# Format code with ruff
fmt *args=".":
    uv run ruff format {{args}}

# Lint with ruff
lint *args=".":
    uv run ruff check {{args}}

# Type-check with ty
ty *args=".":
    uvx ty check {{args}}

# Test recipe: auto-format, lint, type-check, and unit test
# Usage:
#   just test        # runs checks on modified Python files
#   just test all    # runs checks and tests across the full codebase
test scope="modified":
    #!/usr/bin/env bash
    set -euo pipefail
    if [ "{{scope}}" = "all" ]; then
        echo "Running full verification (format, lint, ty, pytest)..."
        uv run ruff format .
        uv run ruff check --fix .
        uvx ty check .
        uv run pytest
    else
        MODIFIED=$(git diff --name-only HEAD | grep -E '\.py$' || true)
        UNTRACKED=$(git ls-files --others --exclude-standard | grep -E '\.py$' || true)
        FILES=$(echo -e "${MODIFIED}\n${UNTRACKED}" | sed '/^$/d' | sort -u | tr '\n' ' ')
        if [ -z "${FILES}" ]; then
            echo "No modified Python files detected. Running full pytest suite..."
            uv run pytest
        else
            echo "Running checks on modified files: ${FILES}"
            uv run ruff format ${FILES}
            uv run ruff check --fix ${FILES}
            uvx ty check ${FILES}
            uv run pytest
        fi
    fi

# Dispatch a GitHub Actions workflow using gh CLI
# Usage: just run-workflow release.yml -f ref=main
run-workflow *args="--help":
    gh workflow run {{args}}

# Run the release-notes automation
run-release-notes *args="--help":
    uv run automations/release_notes.py {{args}}

# Run the signal-to-issue automation
run-signal-to-issue *args="--help":
    uv run automations/signal_to_issue.py {{args}}

# Remove generated artifacts (never the environment itself — that's `down`)
clean:
    rm -rf .pytest_cache .ruff_cache reports dist
    find . -name '__pycache__' -type d -prune -exec rm -rf {} +
