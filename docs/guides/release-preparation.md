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
strict Sphinx HTML, and CLI smoke tests. API docstrings with `>>>` examples are
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

The release workflow can tag and create a GitHub Release after successful main
CI when that version has no tag. PyPI/TestPyPI uploads use the explicit workflow
input and configured repository credentials. Review the version and release
notes before merging; a documentation preparation pass does not publish a release.
