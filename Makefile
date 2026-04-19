.PHONY: install test test-cov lint typecheck format recipe clean help

PY ?= python
RECIPE ?=

help:
	@echo "Claude Agent Cookbook — common tasks"
	@echo ""
	@echo "  make install        Install runtime + dev dependencies"
	@echo "  make test           Run all unit tests (no API key needed)"
	@echo "  make test-cov       Run tests with coverage report (target: 80%)"
	@echo "  make lint           Run ruff lint checks"
	@echo "  make typecheck      Run mypy strict on common/"
	@echo "  make format         Format code with black + ruff autofix"
	@echo "  make recipe NAME=01-tool-use    Run a specific recipe end-to-end"
	@echo "  make clean          Remove caches and build artifacts"

install:
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -r requirements.txt

test:
	$(PY) -m pytest -q

test-cov:
	$(PY) -m pytest --cov=common --cov-report=term-missing --cov-report=xml

lint:
	$(PY) -m ruff check common recipes

typecheck:
	$(PY) -m mypy common

format:
	$(PY) -m black common recipes
	$(PY) -m ruff check --fix common recipes

recipe:
ifndef NAME
	$(error NAME is required. Usage: make recipe NAME=01-tool-use)
endif
	$(PY) recipes/$(NAME)/recipe.py

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage coverage.xml htmlcov
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
