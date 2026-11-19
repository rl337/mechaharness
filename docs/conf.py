"""Sphinx configuration for MechaHarness documentation."""

from __future__ import annotations

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.abspath("../src"))

project = "MechaHarness"
copyright = f"{datetime.now().year}, Richard Lee"
author = "Richard Lee"

try:
    import mechaharness

    release = mechaharness.__version__
    version = ".".join(release.split(".")[:2])
except ImportError:
    release = "0.1.0"
    version = "0.1"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
    "sphinx.ext.napoleon",
    "myst_parser",
]

autodoc_default_options = {
    "members": True,
    "undoc-members": True,
    "show-inheritance": True,
    "special-members": "__init__",
}

autosummary_generate = True

napoleon_google_docstring = True
napoleon_numpy_docstring = True
napoleon_include_init_with_doc = False
napoleon_include_private_with_doc = False

html_theme = "sphinx_rtd_theme"
html_theme_options = {
    "style_nav_header_background": "#0066cc",
    "collapse_navigation": False,
    "sticky_navigation": True,
    "navigation_depth": 2,
    "titles_only": True,
}

html_static_path = ["_static"]
html_css_files = ["custom.css"]
html_logo = "logo.png"

html_context = {
    "display_github": True,
    "github_user": "rl337",
    "github_repo": "mechaharness",
    "github_version": "main",
    "conf_py_path": "/docs/",
    "version": release,
}

# API pages use local defining-module targets; builds need no remote inventories.
intersphinx_mapping: dict[str, tuple[str, None]] = {}

htmlhelp_basename = "mechaharnessdoc"

exclude_patterns = [
    "_build",
    "plans/**",  # local-only planning, never part of the published documentation
    "adr/**",  # local-only decision notes
    "Thumbs.db",
    ".DS_Store",
    "index.md",  # Sphinx home is index.rst; keep markdown TOC for GitHub browsing
    "templates.md",
]

source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

master_doc = "index"

myst_enable_extensions = [
    "colon_fence",
]

# Prefer defining-module targets when names are also re-exported at package root.
autodoc_type_aliases = {
    "EventLog": "mechaharness.core.events.EventLog",
    "Event": "mechaharness.core.events.Event",
    "EventType": "mechaharness.core.events.EventType",
    "AccessControl": "mechaharness.core.access.AccessControl",
    "CostAccountant": "mechaharness.core.access.CostAccountant",
    "Settings": "mechaharness.config.Settings",
    "MechaHarnessConfig": "mechaharness.di.MechaHarnessConfig",
    "SettingsConfig": "mechaharness.di.SettingsConfig",
}

# Resolve Markdown heading links consistently in the published site.
myst_heading_anchors = 4

# Preserve published HTML URLs when overlapping Markdown pages are consolidated.
templates_path = ["_templates"]
_DOCUMENT_REDIRECTS = {
    "guides/user-story-migration-batches": "authoring-user-stories.html",
    "guides/user-story-instrumentation-migration": "authoring-user-stories.html",
    "guides/user-story-recipe-expansion": "authoring-user-stories.html",
    "guides/release-refactor-priorities": "../architecture.html#integration-boundaries",
    "inspiration/trouble-context-attrition-2026-10-29": "trouble.html#context-attrition",
    "inspiration/trouble-realm-resource-scope-and-memory-safety-2026-11-03":
        "trouble.html#resource-scope-and-memory",
    "inspiration/trouble-prefixwise-cache-regression-2026-11-10":
        "trouble.html#request-prefix-caching",
    "inspiration/trouble-trace-and-requirement-integrity-2026-11-17":
        "trouble.html#trace-and-requirement-integrity",
    "inspiration/trouble-release-status": "trouble.html#implementation-status",
}


def _redirect_pages(app):
    for old, target in _DOCUMENT_REDIRECTS.items():
        yield old, {"target": target}, "redirect.html"


def setup(app):
    app.connect("html-collect-pages", _redirect_pages)
