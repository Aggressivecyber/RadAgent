.PHONY: lint typecheck test test-all test-real-full-graph format clean setup-env nist-reference nist-geant4-smoke nist-reproduce

lint:
	ruff check .

typecheck:
	mypy agent_core/ --ignore-missing-imports

test:
	pytest tests/unit/ -v --tb=short

test-all:
	pytest tests/ -v --tb=short

test-real-full-graph:
	python scripts/run_real_full_graph_test.py

setup-env:
	./scripts/setup_radagent_env.sh

nist-reference:
	./scripts/reproduce_nist_benchmark.sh --reference-only --output-dir benchmarks/reports

nist-geant4-smoke:
	./scripts/reproduce_nist_benchmark.sh --events 1000 --case-limit 2 --output-dir benchmarks/reports/nist_smoke

nist-reproduce:
	./scripts/reproduce_nist_benchmark.sh --output-dir benchmarks/reports

format:
	ruff format agent_core/ tests/ scripts/

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache .mypy_cache .ruff_cache
	rm -rf simulation_workspace/jobs/* simulation_workspace/logs simulation_workspace/.cache simulation_workspace/radagent.db
	mkdir -p simulation_workspace/jobs
	touch simulation_workspace/jobs/.gitkeep
