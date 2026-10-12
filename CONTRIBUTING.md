# Contributing to FORGEX

We welcome contributions!

## Development Setup

```bash
git clone https://github.com/B-max12/Forgex.git
cd Forgex
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Running Tests and Linting

```bash
pytest -q
ruff check .
mypy src
```

## Core Principles

1. Honesty: Never claim tests passed unless actually verified.
2. Safety: All agent tools must respect workspace confinement and permissions.
3. Quality: New features must include unit tests.
