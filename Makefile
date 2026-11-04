.PHONY: install gemini-version test test-all lint format

install:
	python -m pip install "pip>=25.1"
	python -m pip install -r requirements/gemini.txt
	python scripts/project_dependencies.py | python -m pip install -r /dev/stdin
	python -m pip install --group dev

gemini-version:
	@python -c "import gemini; print(gemini.__version__)"

test:
	python scripts/test_changed.py

test-all:
	python -m pytest -m "not slow and not docker" --profile=development

lint:
	flake8 geomind tests examples scripts evals
	black --check geomind tests examples scripts evals
	isort --check-only geomind tests examples scripts evals

format:
	black geomind tests examples scripts evals
	isort geomind tests examples scripts evals
