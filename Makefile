PY = .venv/bin/python
PYTHON ?= python3
OFFLINE = PYTHON_DOTENV_DISABLED=1 CLASSIFIER=offline JUDGE=off LANGSMITH_TRACING=false LEASH_TODAY=2026-03-15

.PHONY: setup check test clean demo chat eval eval-llm eval-judge eval-langsmith graph
setup:
	@if command -v uv >/dev/null; then uv sync --locked; else $(PYTHON) -m venv .venv && $(PY) -m pip install -r requirements.lock && $(PY) -m pip install --no-deps -e .; fi

check:
	.venv/bin/ruff check .
	.venv/bin/ruff format --check .
	$(PY) -m mypy
	$(OFFLINE) $(MAKE) test
	$(OFFLINE) $(MAKE) eval

test:
	$(PY) -m pytest -q

demo chat graph eval-langsmith:
	@$(PY) -m src.cli $@

eval:
	@CLASSIFIER=offline $(PY) -m src.cli eval

eval-llm:
	@CLASSIFIER=llm $(PY) -m src.cli eval

eval-judge:
	@JUDGE=llm $(PY) -m src.cli eval

clean:
	rm -rf .venv .ruff_cache .mypy_cache build
