# Prepare and publish a release

Versions are chosen in a reviewed commit. Releases run only through the manual
**Release** workflow on `main` or `master`. Merging a PR neither bumps the version
nor publishes a package.

## Prepare the candidate

1. Choose the version after reviewing compatibility changes. Set the same final
   `X.Y.Z` in `pyproject.toml` and `src/mechaharness/__init__.py`.
2. Move the relevant `CHANGELOG.md` Unreleased notes into a dated version entry.
3. Review [user stories](./user-stories.md), API examples, host skills, and any
   [open inspiration requirements](../inspiration/trouble.md#implementation-status).
4. Install `pip install -e '.[dev,docs]'`, run
   `MECHA_STORY_BACKEND=static ./run_checks.sh`, then commit the candidate.

Checks include repository hygiene, lint, types, doctests, schema and attribution
validation, generated-document checks, story coverage, strict Sphinx, and CLI
smoke tests. Story sources and generation commands are described in
[authoring user stories](./authoring-user-stories.md).

The repository hygiene scan has a limited signature set. Inspect package
contents and changed examples as well; a clean scan does not prove the absence
of every possible secret.

## Validate package identity locally

From a clean candidate checkout, use a fresh output directory:

```bash
python scripts/release_candidate.py --expected-sha "$(git rev-parse HEAD)"
python -m build --outdir /tmp/mechaharness-dist
python -m twine check /tmp/mechaharness-dist/*
python scripts/release_candidate.py --expected-sha "$(git rev-parse HEAD)" \
  --dist /tmp/mechaharness-dist
```

The validator rejects mismatched package versions, a different checkout SHA,
modified or untracked candidate files, conflicting version tags, and archives
containing untracked or changed source. Build output and tool caches must stay
in the documented ignored paths. Archive metadata must match the selected
version. API `>>>` examples run through pytest without network access.

## Dispatch the release

After merging the reviewed candidate, run **Actions → Release → Run workflow**
on the release branch. The run pins the dispatch SHA even if main later advances.
A single concurrency group serializes release attempts without cancelling an
active release. That same checkout passes the full checks, builds both archives,
and validates their identity before tagging.

Set `publish_target` to:

- `none` to create GitHub release artifacts only;
- `testpypi` for a pipeline smoke release;
- `pypi` for the final public package.

Configure Trusted Publishing for owner `rl337`, repository `mechaharness`,
workflow `release.yml`. Registry publication has access to its OIDC credentials
only in the publish job after the package job succeeds.

A matching existing tag permits a retry, but a tag pointing to another commit
fails and is never moved. Existing published GitHub releases with the matching tag are preserved.
Unexpected drafts/prereleases and API errors fail explicitly; only an HTTP 404
permits creating a missing release. Registry
uploads fail if the version already exists; investigate the prior run and select
a new version when needed rather than treating an unrelated existing package as
success. A failed validation run cannot tag or publish. No automatic version-bump
workflow runs after CI.

Documentation is deployed separately by `docs.yml`: main owns the production
site and PRs have branch previews. Documentation cleanup does not publish a
package or move release tags.
