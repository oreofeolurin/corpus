PYTHON ?= python3
PIP ?= $(PYTHON) -m pip

.PHONY: help install-dev test build wheel sdist binary docker-build docker-run clean bump-version

help:
	@echo "Targets: install-dev, test, build, wheel, sdist, binary, docker-build, docker-run, clean, bump-version"

install-dev:
	$(PIP) install --upgrade pip
	$(PIP) install -e .
	$(PIP) install pytest pyinstaller build

test:
	pytest -q

build: wheel sdist

wheel:
	$(PYTHON) -m build --wheel

sdist:
	$(PYTHON) -m build --sdist

binary:
	pyinstaller --name corpus --onefile corpus/__main__.py

docker-build:
	docker build -t oreofeolurin/corpus:latest .

docker-run:
	docker run --rm -it -v $$PWD/artifacts:/data oreofeolurin/corpus:latest --help

clean:
	rm -rf build dist *.spec __pycache__ .pytest_cache

bump-version:
	@echo "Usage: make bump-version TYPE"
	@echo "  TYPE can be: patch, minor, major, or a specific version like 0.2.5"
	@echo "  Examples:"
	@echo "    make bump-version patch"
	@echo "    make bump-version 0.2.5"
	@if [ -z "$(TYPE)" ]; then echo "Error: TYPE is required"; exit 1; fi
	$(PYTHON) scripts/bump_version.py $(TYPE)


