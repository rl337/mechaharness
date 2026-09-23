# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Sphinx documentation published at https://rl337.org/mechaharness/
- PyPI packaging metadata, Trusted Publishing release workflow, and auto version bump

### Changed

- `junespark` backend no longer ships a private LAN `base_url` default; set `MECHA_BASE_URL`

### Security

- Purged historical `REQUIREMENTS.md` (host LAN inventory) from git history prior to public release
