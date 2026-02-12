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

## License

By contributing, you agree that your contributions will be licensed under the [GPL-3.0 License](LICENSE).
