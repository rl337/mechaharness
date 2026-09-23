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

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}

htmlhelp_basename = "mechaharnessdoc"

exclude_patterns = [
    "_build",
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
