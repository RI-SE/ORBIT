# Contributing to ORBIT

Thank you for your interest in contributing to ORBIT! This document outlines the process for contributing to the project.

## Reporting Bugs

Open a [GitHub issue](https://github.com/RI-SE/ORBIT/issues) with the following information:

- Steps to reproduce the problem
- Expected behavior vs. actual behavior
- OS and Python version
- ORBIT version (shown in Help > About)
- Any relevant screenshots or `.orbit` project files

## Proposing Features

Open a [GitHub issue](https://github.com/RI-SE/ORBIT/issues) and describe:

- The use case — what problem does this solve?
- Proposed behavior
- Any relevant OpenDRIVE specification details, if applicable

## Development Setup

**Requirements:** Python 3.10+

```bash
git clone https://github.com/RI-SE/ORBIT.git
cd ORBIT
uv sync --extra dev
```

Verify the setup by running the tests:

```bash
uv run python -m pytest tests/ -v
```

## Pull Request Process

1. Fork the repository and create a branch from `main`.
2. Make your changes.
3. Run linting and tests (see below).
4. Submit a pull request against `main` with a clear description of the changes.

Keep PRs focused — one feature or fix per PR.

## Code Style

**Linting** is enforced with ruff:

```bash
uv run ruff check orbit/ tests/ run_orbit.py
```

**General rules:**

- Type hints on all function signatures.
- Docstrings on public functions. Avoid restating what is obvious from the code.
- Import order: standard library, third-party, local (enforced by ruff/isort).

## Testing

Run the full test suite:

```bash
uv run python -m pytest tests/ -v
```

- New features should include tests where feasible.
- Don't break existing tests.

## Extension points and module ownership

Use this map to decide where changes belong:

- `orbit/models/`: core dataclasses and serialization (`to_dict` / `from_dict`).
- `orbit/gui/`: Qt UI wiring, interaction handling, and undo commands.
- `orbit/import/`: OSM/OpenDRIVE ingestion and conversion into model objects.
- `orbit/export/`: OpenDRIVE/OSM output generation from project state.
- `orbit/utils/`: shared geometry, coordinate transform, validation, logging helpers.

When adding behavior, prefer placing logic in `models`, `import`, `export`, or `utils` and keeping GUI files focused on orchestration.

## AI-friendly maintainability checklist

- Keep new functions small and single-purpose.
- Avoid hidden cross-module side effects; make data flow explicit.
- Reuse existing helpers before introducing near-duplicates.
- Add or update tests in the same PR as behavior changes.
- Update docs when changing extension points or module boundaries.

## Maintainability baseline report

To track large files/functions and coverage hotspots:

```bash
QT_QPA_PLATFORM=offscreen uv run python -m pytest tests/ --cov=orbit --cov-report=json:temp/coverage.json
uv run python tools/maintainability_report.py --coverage-json temp/coverage.json
```

## License

By contributing, you agree that your contributions will be licensed under the [GPL-3.0 License](LICENSE).
