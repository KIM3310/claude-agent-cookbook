#!/usr/bin/env bash
# Convenience wrapper for running cookbook recipes.
# Usage: scripts/run_recipe.sh 01-tool-use [--prompt "..."]

set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <recipe-name> [extra args...]" >&2
  echo "Example: $0 01-tool-use --prompt \"Weather in Seoul\"" >&2
  exit 2
fi

RECIPE="$1"
shift

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RECIPE_DIR="$ROOT/recipes/$RECIPE"

if [[ ! -d "$RECIPE_DIR" ]]; then
  echo "Recipe not found: $RECIPE_DIR" >&2
  exit 1
fi

if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
  if [[ -f "$ROOT/.env" ]]; then
    # shellcheck disable=SC1091
    set -a && source "$ROOT/.env" && set +a
  fi
fi

if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
  echo "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and fill it in." >&2
  exit 1
fi

cd "$ROOT"
exec python "$RECIPE_DIR/recipe.py" "$@"
