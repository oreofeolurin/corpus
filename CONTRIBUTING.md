# Contributing

Thanks for your interest in contributing! This project welcomes PRs and issues.

## Getting Started

- Python 3.9+
- Install dev deps:
```bash
make install-dev
```
- Run tests:
```bash
make test
```

## Development

- Add tests for new features and bug fixes
- Keep CLI help concise; detailed docs go in README/docs
- Run `make build` before release PRs

## Release

- Bump version in `corpus/__init__.py` and `pyproject.toml`
- Tag `vX.Y.Z` to trigger release workflows

## Code Style

- Prefer clear naming and small functions
- Avoid unnecessary global state
- Keep stdout clean for `--json`; logs to stderr
