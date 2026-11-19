# Prepare a release

Start with a clean checkout of the intended release commit. Review open pull
requests and the [Trouble implementation gaps](../inspiration/trouble-release-status.md)
before describing a feature as complete. Static acceptance proves recorded
behavior; record any live validation separately with its provider and model.

## Check documentation and stories

Install the development and documentation tools:

```bash
pip install -e '.[dev,docs]'
```

Review changed API contracts and examples against their defining modules.
Keep README focused on installation and a first run; put detailed host setup
in task guides and exact contracts in reference pages. Include downstream
`agent-skills/` when changing host integration guidance.

Read story stage YAML as an operational walk: persona and goal, host setup,
actions, and observable completion. Each stage needs `id`, `suite`, `persona`,
`title`, `narrative`, `implementation`, `validation`, and `footnotes` (use `[]`
when there is no attribution). Implementation and validation must describe what
the walk actually proves. Keep HTTP twin prose identical to its static story.

After changing story source files, regenerate the artifacts:

```bash
python -m tests.stories.commands sync-suites
python -m tests.stories.commands sync-guide
```

## Verify the release candidate

```bash
MECHA_STORY_BACKEND=static ./run_checks.sh
python -m build --outdir /tmp/mechaharness-dist
python -m twine check /tmp/mechaharness-dist/*
```

Use a fresh output directory for each package build. The checks run lint, types,
story schema and attribution validation, doctests, unit tests, story coverage,
strict Sphinx HTML, repository hygiene, and CLI smoke tests. API docstrings with `>>>` examples are
collected by pytest from `src/mechaharness`; examples should run without network
access. Recipe catalog tests also require public recipe documentation and
examples. Sphinx warnings fail both local checks and the documentation workflow.

Check the wheel and source archive contain the package and `py.typed`, and
exclude env scripts, credentials, local plans, and runtime state. Put the user
visible changes and any remaining limitations in `CHANGELOG.md` under Unreleased.

## Choose and publish the version

Choose the version after reviewing the final diff and compatibility impact.
Update `pyproject.toml` and move the Unreleased notes into a dated entry for that
version. Verify the package reports the same version.

Current automation has two independent workflows after main CI: **Auto Version
Bump** changes `pyproject.toml` and `src/mechaharness/__init__.py` on the live
branch (patch for a regular commit, minor for a merge); **Release** packages the
original CI-tested SHA and tags its version if absent. Bump commits use
`[skip ci]`. They are not an ordered release pipeline. Resolve the
[commit/version sequencing gap](./release-refactor-priorities.md) before the next
automated release.

For an explicitly chosen release version, keep both version declarations in
sync and validate the exact candidate commit before packaging. The release
workflow can tag and create a GitHub Release when that version has no tag. PyPI/TestPyPI uploads use the explicit workflow
input and configured repository credentials. Review the version and release
notes before merging; a documentation preparation pass does not publish a release.


For index uploads, configure PyPI/TestPyPI Trusted Publishing for owner `rl337`,
repository `mechaharness`, workflow `release.yml`. Use the explicit
`publish_target` input: `none` for GitHub artifacts only, `testpypi` for pipeline
smoke validation, then `pypi` for the final immutable version. Repeating an
existing version uses `skip-existing`; it does not replace a published package.
Documentation deployment uses `.github/workflows/docs.yml`, which publishes
main at the site root and PR previews under `branch/`.
