# Repo command standards. Every repo gets the same recipes:
# up / down / lint / ty / test / clean / run

set dotenv-load

# Bring the dev environment up
up:
    uv sync

# Tear the dev environment down
down:
    rm -rf .venv

# Lint with ruff
lint:
    uv run ruff check .

# Type-check with ty
ty:
    uvx ty check .

# Run the test suite
test:
    uv run pytest

# Remove generated artifacts (never the environment itself — that's `down`)
clean:
    rm -rf .pytest_cache .ruff_cache reports dist
    find . -name '__pycache__' -type d -prune -exec rm -rf {} +

# Run the release-notes example (args pass through, e.g. `just run -- --help`)
run *args="--help":
    uv run automations/release_notes.py {{args}}
