.PHONY: all clean dev lint typecheck test build run flatpak flatpak-install

UV := uv run
PYTHON := $(UV) python
FLATPAK_APP_ID := io.github.shanril.sobornost
FLATPAK_MANIFEST := packaging/flatpak/$(FLATPAK_APP_ID).yml
FLATPAK_BUILD_DIR := build/flatpak
FLATPAK_REPO_DIR := build/flatpak-repo
FLATPAK_BUNDLE := dist/sobornost-x86_64.flatpak

all: build

# TODO(phase-6-packaging): this target still drives the py2app backend, which
# was built for Tkinter bundling (signal routing, TCL/TK dylibs) and has not
# been reworked for PySide6. It will NOT produce a runnable PySide6 .app
# (missing Qt framework bundling / qt.conf). Do not treat a successful exit
# as a working bundle; that work is deferred to the Phase 6 packaging pass.
build: uv-sync
	@$(PYTHON) setup.py py2app

dev: uv-sync
	$(PYTHON) -m sobornost

run: build
	open dist/sobornost.app

flatpak:
	mkdir -p dist
	flatpak-builder --arch=x86_64 --force-clean --user --install-deps-from=flathub \
		--repo=$(FLATPAK_REPO_DIR) $(FLATPAK_BUILD_DIR) $(FLATPAK_MANIFEST)
	flatpak build-bundle --arch=x86_64 \
		--runtime-repo=https://flathub.org/repo/flathub.flatpakrepo \
		$(FLATPAK_REPO_DIR) $(FLATPAK_BUNDLE) $(FLATPAK_APP_ID)

flatpak-install: flatpak
	flatpak install --user --reinstall --yes $(FLATPAK_BUNDLE)

lint: uv-sync
	$(UV) ruff check .

typecheck: uv-sync
	$(UV) mypy sobornost/

test: uv-sync
	$(UV) pytest

clean:
	rm -rf build/ dist/ .venv/ .mypy_cache/ .pytest_cache/ .ruff_cache/ *.egg-info/
	rm -f packaging/sobornost.app/Contents/MacOS/sobornost
	rm -f uv.lock
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true
	find . -type d -name '*.pyc' -delete 2>/dev/null; true
	find . -name '*.so' -delete 2>/dev/null; true

uv-sync:
	uv sync
