.PHONY: install test test-all lint format

install:
	python -m pip install -e ../gemini -e . --group dev

test:
	python scripts/test_changed.py

test-all:
	python -m pytest -m "not slow and not docker" --profile=development

lint:
	flake8 geomind tests examples scripts
	black --check geomind tests examples scripts
	isort --check-only geomind tests examples scripts

format:
	black geomind tests examples scripts
	isort geomind tests examples scripts
