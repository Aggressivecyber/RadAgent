.PHONY: lint typecheck test test-all format clean

lint:
	ruff check agent_core/ tests/

typecheck:
	mypy agent_core/ --ignore-missing-imports

test:
	pytest tests/unit/ -v --tb=short

test-all:
	pytest tests/ -v --tb=short

format:
	ruff format agent_core/ tests/

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache .mypy_cache .ruff_cache
