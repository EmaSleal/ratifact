# Publishing ratifact (GitHub + PyPI)

Steps for the maintainer (ADR-015: GitHub + PyPI, installed with `uv tool install ratifact` / `uvx ratifact`). Nothing
here has been done yet: the repository is not public and nothing was uploaded to PyPI.

Repository: <https://github.com/EmaSleal/ratifact> (GitHub user `EmaSleal`; `[project.urls]` in `pyproject.toml`).

## 0. Before publishing

- `uv run --with pytest --with "mcp>=1.2,<2" pytest -q` passes (it includes `tests/test_datos_personales.py`: no
  `/home/<user>` paths nor e-mail addresses in versioned files).
- The version in `pyproject.toml` and `ratifact/__init__.py` is the one to publish (`1.0.0`).
- `uv build && uvx twine check dist/*` passes locally.
- The history does not contain `projects.json` (`git log --all --full-history -- projects.json` prints nothing).
  Commit metadata (author name and e-mail) is public once pushed; rewriting history is out of scope.

## 1. Create the GitHub repository

1. On GitHub: *New repository* → name `ratifact`, public, **without** README, license or .gitignore (they already
   exist here).
2. Locally:
   ```
   git remote add origin https://github.com/EmaSleal/ratifact.git
   git push -u origin main
   ```
3. Check that the `tests` workflow (`.github/workflows/tests.yml`: Linux and macOS, Python 3.10–3.13, no global git
   identity) passes on `main`.

## 2. Configure PyPI trusted publishing

The name `ratifact` was free on PyPI on 2026-10-20. Trusted publishing (OIDC) lets the workflow upload without any
token stored in GitHub.

1. Sign in to <https://pypi.org> (enable 2FA).
2. *Your account* → *Publishing* → *Add a new pending publisher* (the project does not exist yet):
   - PyPI project name: `ratifact`
   - Owner: `EmaSleal`
   - Repository name: `ratifact`
   - Workflow name: `publish.yml`
   - Environment name: `pypi`
3. On GitHub: *Settings* → *Environments* → *New environment* `pypi` (optionally with *Required reviewers* and a
   deployment rule for tags `v*`).

## 3. Publish v1.0.0

```
git tag -a v1.0.0 -m "ratifact 1.0.0"
git push origin v1.0.0
```

The `publish` workflow checks that the tag matches `version` in `pyproject.toml`, builds the sdist and the wheel, runs
`twine check` and uploads them through trusted publishing. Afterwards:

```
uvx ratifact --version        # ratifact 1.0.0
uv tool install ratifact
ratifact install              # plan
```

## Next releases

Bump `version` in `pyproject.toml` and `__version__` in `ratifact/__init__.py` (a test checks they match), merge into
`main`, then tag `vX.Y.Z` and push the tag.
