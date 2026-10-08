# Makefile for nps-ctl package

# Variables
PACKAGE_NAME := nps-ctl
DIST_DIR := dist
VERSION := $(shell python -c "import re; m=re.search(r'__version__\s*=\s*\"(.+?)\"', open('src/nps_ctl/__init__.py').read()); print(m.group(1))" 2>/dev/null || echo "0.0.0")

# Registry mirror (for Docker-based musl builds)
REGISTRY_MIRROR ?=

# Default target
all: lint test build

# ──────────────────────────────────────────────
# Linting & Type Checking
# ──────────────────────────────────────────────

# Run ruff and ty checks
lint:
	@echo "Running ruff check..."
	ruff check src/
	@echo "Running ruff format check..."
	ruff format --check src/
	@echo "Running ty check..."
	ty check src/
	@echo "All checks passed."

# Auto-fix lint issues
fix:
	@echo "Running ruff fix..."
	ruff check --fix src/
	@echo "Running ruff format..."
	ruff format src/
	@echo "Fix complete."

# ──────────────────────────────────────────────
# Testing
# ──────────────────────────────────────────────

# Run tests
test:
	@echo "Running tests..."
	pytest tests/ -v --tb=short
	@echo "Tests completed."

# ──────────────────────────────────────────────
# Package targets
# ──────────────────────────────────────────────

# Build the package
build: clean
	@echo "Building $(PACKAGE_NAME)..."
	python -m build
	@echo "Build complete. Distribution files are in $(DIST_DIR)/"

# Push the package to PyPI
push:
	@echo "Pushing $(PACKAGE_NAME) to PyPI..."
	twine upload dist/*
	@echo "Package pushed to PyPI."

# Clean up build and distribution files
clean:
	@echo "Cleaning up build and distribution files..."
	rm -rf $(DIST_DIR) *.egg-info src/*.egg-info
	@echo "Cleanup complete."

# ──────────────────────────────────────────────
# Nuitka binary builds
# ──────────────────────────────────────────────

UNAME_S := $(shell uname -s 2>/dev/null || echo Windows)
UNAME_M := $(shell uname -m 2>/dev/null || echo x86_64)
ifeq ($(UNAME_S),Linux)
  BINARY_OS := linux
else ifeq ($(UNAME_S),Darwin)
  BINARY_OS := macos
else
  BINARY_OS := windows
endif
ifeq ($(filter arm64 aarch64,$(UNAME_M)),)
  BINARY_ARCH := x86_64
else
  BINARY_ARCH := arm64
endif

BINARY_NAME = nps-ctl-$(VERSION)-$(BINARY_OS)-$(BINARY_ARCH)
BINARY_NAME_MUSL = nps-ctl-$(VERSION)-linux-$(BINARY_ARCH)-musl
BINARY_DIR := build
NUITKA_ENTRY := _nuitka_entry.py
NUITKA_JOBS := $(shell nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 2)
NUITKA_EXTRA_FLAGS ?=

# Aggressively exclude stdlib modules not used by nps-ctl or rich.
# nps-ctl uses: argparse, base64, dataclasses, enum, hashlib, json, logging,
#   os, pathlib, random, secrets, signal, socket, ssl, subprocess, sys,
#   threading, time, tomllib, typing, urllib, concurrent.futures, atexit
# rich uses: html.parser, inspect, os, re, sys, threading, typing, shutil
NUITKA_NOFOLLOW := \
	pytest setuptools pip _pytest \
	tkinter unittest pydoc doctest test \
	distutils ensurepip idlelib lib2to3 \
	turtle turtledemo xmlrpc curses \
	asyncio email sqlite3 csv \
	pdb cProfile profile trace \
	ftplib imaplib poplib smtplib nntplib telnetlib \
	xml.sax xml.dom xml.etree \
	http.server http.cookiejar \
	zipapp compileall py_compile \
	webbrowser antigravity this \
	gettext optparse \
	cgitb tabnanny symtable

NUITKA_NOFOLLOW_FLAGS := $(foreach m,$(NUITKA_NOFOLLOW),--nofollow-import-to=$m)

NUITKA_FLAGS = \
	--standalone \
	--onefile \
	--jobs=$(NUITKA_JOBS) \
	--output-dir=$(BINARY_DIR) \
	--lto=yes \
	--python-flag=no_docstrings \
	--python-flag=-O \
	--python-flag=no_warnings \
	--python-flag=no_site \
	--include-package=nps_ctl \
	$(NUITKA_NOFOLLOW_FLAGS) \
	--assume-yes-for-downloads \
	$(NUITKA_EXTRA_FLAGS)

build-binary:
	@echo "Building native binary: $(BINARY_NAME)..."
	@printf 'from nps_ctl.cli import main\nmain()\n' > $(NUITKA_ENTRY)
	python -m nuitka $(NUITKA_FLAGS) \
		--output-filename=$(BINARY_NAME)$(if $(filter windows,$(BINARY_OS)),.exe,) \
		$(NUITKA_ENTRY); \
	ret=$$?; rm -f $(NUITKA_ENTRY); exit $$ret
	@ls -lh $(BINARY_DIR)/$(BINARY_NAME)*
	@echo "Binary build complete."

build-binary-musl:
	@echo "Building musl binary: $(BINARY_NAME_MUSL)..."
	@mkdir -p $(BINARY_DIR)
	docker run --rm \
		-v $(CURDIR):/workspace:ro \
		-v $(CURDIR)/$(BINARY_DIR):/output \
		$(if $(REGISTRY_MIRROR),$(REGISTRY_MIRROR)/)python:3.12-alpine \
		/bin/sh -c '\
			mkdir -p /tmp/build && tar -cf - -C /workspace --exclude=.git --exclude=__pycache__ . | tar -xf - -C /tmp/build && cd /tmp/build && \
			apk add --no-cache gcc musl-dev python3-dev git >/dev/null && \
			pip install --break-system-packages patchelf -q && \
			pip install --break-system-packages -e "." -q && \
			pip install --break-system-packages "nuitka[onefile]" ordered-set -q && \
			printf "from nps_ctl.cli import main\nmain()\n" > /tmp/_entry.py && \
			python -m nuitka \
				--standalone --onefile \
				--jobs=$$(nproc) \
				--output-dir=/output \
				--output-filename=$(BINARY_NAME_MUSL) \
				--lto=yes \
				--python-flag=no_docstrings \
				--python-flag=-O \
				--python-flag=no_warnings \
				--python-flag=no_site \
				--include-package=nps_ctl \
				$(NUITKA_NOFOLLOW_FLAGS) \
				--assume-yes-for-downloads \
				$(NUITKA_EXTRA_FLAGS) \
				/tmp/_entry.py && \
			rm -rf /output/_entry.* '
	@ls -lh $(BINARY_DIR)/$(BINARY_NAME_MUSL)
	@echo "Musl binary build complete."

clean-binary:
	@echo "Cleaning binary build artifacts..."
	rm -rf $(BINARY_DIR)/_nuitka_entry.* $(BINARY_DIR)/_entry.* $(NUITKA_ENTRY)
	@echo "Clean complete. Binaries in $(BINARY_DIR)/ preserved."

clean-binary-all:
	@echo "Cleaning all binary artifacts..."
	rm -rf $(BINARY_DIR)
	rm -f $(NUITKA_ENTRY)
	@echo "Clean complete."

# ──────────────────────────────────────────────
# Help
# ──────────────────────────────────────────────

help:
	@echo "Available targets:"
	@echo ""
	@echo "Development:"
	@echo "  lint              - Run ruff and ty checks"
	@echo "  fix               - Auto-fix ruff lint and format issues"
	@echo "  test              - Run tests with pytest"
	@echo ""
	@echo "Package targets:"
	@echo "  build             - Build the pip package"
	@echo "  push              - Push the package to PyPI"
	@echo "  clean             - Clean up build and distribution files"
	@echo ""
	@echo "Binary targets:"
	@echo "  build-binary      - Build native Nuitka binary for current platform"
	@echo "  build-binary-musl - Build musl-linked binary via Alpine Docker"
	@echo "  clean-binary      - Clean build artifacts (keep binaries)"
	@echo "  clean-binary-all  - Clean all binary artifacts"
	@echo ""
	@echo "Composite targets:"
	@echo "  all               - Run lint, test, and build (default)"
	@echo ""
	@echo "Variables:"
	@echo "  REGISTRY_MIRROR=<host> - Docker registry mirror"
	@echo "  NUITKA_EXTRA_FLAGS=... - Extra Nuitka flags"

.PHONY: all lint fix test build push clean help \
	build-binary build-binary-musl clean-binary clean-binary-all
