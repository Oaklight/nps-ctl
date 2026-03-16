# Makefile for nps-ctl package

# Variables
PACKAGE_NAME := nps-ctl
DIST_DIR := dist

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

# Help target
help:
	@echo "Available targets:"
	@echo ""
	@echo "Development:"
	@echo "  lint    - Run ruff and ty checks"
	@echo "  fix     - Auto-fix ruff lint and format issues"
	@echo "  test    - Run tests with pytest"
	@echo ""
	@echo "Package targets:"
	@echo "  build   - Build the pip package"
	@echo "  push    - Push the package to PyPI"
	@echo "  clean   - Clean up build and distribution files"
	@echo ""
	@echo "Composite targets:"
	@echo "  all     - Run lint, test, and build (default)"

.PHONY: all lint fix test build push clean help
