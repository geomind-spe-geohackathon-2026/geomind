.PHONY: install test test-all lint format

install:
	python -m pip install -e ../gemini -e . --group dev

test:
	python scripts/test_changed.py

test-all:
	python -m pytest -m "not slow and not docker" --profile=development

lint:
	flake8 swarmax tests examples scripts
	black --check swarmax tests examples scripts
	isort --check-only swarmax tests examples scripts

format:
	black swarmax tests examples scripts
	isort swarmax tests examples scripts
