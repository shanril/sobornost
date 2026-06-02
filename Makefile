.PHONY: all clean dev lint typecheck build run

UV := uv run
PYTHON := $(UV) python

TCL_LIB := $(shell $(PYTHON) -c "import tkinter; print(tkinter.Tcl().eval('info library'))" 2>/dev/null)

all: build

build: uv-sync
	@TCL_LIBRARY=$(TCL_LIB) TK_LIBRARY=$(TCL_LIB) $(PYTHON) setup.py py2app

dev: uv-sync
	$(PYTHON) -m sobornost

run: build
	open dist/sobornost.app

lint: uv-sync
	$(UV) ruff check .

typecheck: uv-sync
	$(UV) mypy sobornost/

clean:
	rm -rf build/ dist/ .venv/ .mypy_cache/ .ruff_cache/ *.egg-info/
	rm -f packaging/sobornost.app/Contents/MacOS/sobornost
    rm -f uv.lock
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true
	find . -type d -name '*.pyc' -delete 2>/dev/null; true
	find . -name '*.so' -delete 2>/dev/null; true

uv-sync:
	uv sync
