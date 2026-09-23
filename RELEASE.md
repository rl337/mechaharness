# Release Process

mechaharness versions live in `pyproject.toml` and
`src/mechaharness/__init__.py`. Patch/minor bumps on `main` are automatic.
**Major versions** (and the first PyPI release, `0.1.0`) are set by hand.

Documentation site: https://rl337.org/mechaharness/

## History note

`REQUIREMENTS.md` (private host inventory) was purged from git history before
the first public PyPI cut. Keep that file gitignored locally; do not re-add it.

## Automatic patch/minor

After CI succeeds on `main`, **Auto Version Bump** increments:

- **Patch** on a regular (including squash) commit
- **Minor** on a merge commit

It does **not** bump when:

- The commit message contains `[skip bump]`
- `pyproject.toml` is already newer than the latest git tag (a manual major)

Those bump commits use `[skip ci]` so they do not loop.

## GitHub Release

The **Release** workflow reads the version already in `pyproject.toml`. It
does not bump. If `vX.Y.Z` is missing, it tags that version, attaches
sdist/wheel, and opens a GitHub Release.

Install line for every production release:

```bash
pip install mechaharness==<version>
```

User-facing notes live in `CHANGELOG.md`. Put new bullets under **Unreleased**
in the same PR; after the auto-bump, move them to `## X.Y.Z`. GitHub Release
bodies should match those bullets.

## Publish to TestPyPI / PyPI

PyPI gets **only** final `X.Y.Z` builds. No RCs, nightlies, or `--pre`.
TestPyPI is a pipeline smoke test, not a user channel.

Trusted Publishing (OIDC) — no API tokens in GitHub secrets:

1. On [TestPyPI publishing](https://test.pypi.org/manage/account/publishing/)
   and [PyPI publishing](https://pypi.org/manage/account/publishing/), add a
   pending publisher: owner `rl337`, repo `mechaharness`, workflow `release.yml`,
   environment left blank.
2. After `0.1.0` is on `main`, **Actions → Release → Run workflow**:
   - First: **publish_target = testpypi**. Confirm
     `pip install -i https://test.pypi.org/simple/ --no-deps mechaharness==0.1.0`.
   - Then: **publish_target = pypi**.

Re-running TestPyPI for the same version is allowed (`skip-existing`).
Production PyPI versions are immutable.

## Manual GitHub Release only

**Actions → Release → Run workflow** with **publish_target = none** tags and
attaches artifacts without uploading to either index.

## Docs / GitHub Pages

The **Documentation** workflow builds Sphinx and deploys to the `gh-pages`
branch (and GitHub Actions Pages). Production URL:

https://rl337.org/mechaharness/

Enable **Settings → Pages → Build and deployment → Source: GitHub Actions**
once per repo if not already set. Confirm org DNS routes `/mechaharness` the
same way `/pyiv` is routed.
