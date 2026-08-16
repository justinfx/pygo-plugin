#!/usr/bin/env bash
# One-shot dev environment setup, see CLAUDE.md "Bootstrapping an environment".
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! command -v go >/dev/null 2>&1; then
    echo "error: 'go' not found on PATH (Go >= 1.24 is required)" >&2
    exit 1
fi
echo "Using $(go version)"

if ! command -v python3 >/dev/null 2>&1; then
    echo "error: 'python3' not found on PATH (Python >= 3.9 is required)" >&2
    exit 1
fi

VENV_DIR="$ROOT/.venv"
if [ -d "$VENV_DIR" ]; then
    echo "Reusing existing virtualenv at $VENV_DIR"
else
    echo "Creating virtualenv at $VENV_DIR"
    python3 -m venv "$VENV_DIR"
fi

"$VENV_DIR/bin/pip" install -q -U pip

echo "Installing pygo-plugin in editable mode"
"$VENV_DIR/bin/pip" install -e ".[test]"

echo "Running tests"
"$VENV_DIR/bin/python" -m pytest ./tests

cat <<EOF

Done. Activate the environment in new shells with:
    source .venv/bin/activate
EOF
