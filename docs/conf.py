"""Build the public handbook without importing MotorFit or hardware backends."""

import json
import os
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
metadata = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]

project = "MotorFit"
author = "MotorFit contributors"
copyright = "2026, MotorFit contributors"
release = metadata["version"]
version = release
docs_version = os.environ.get("MOTORFIT_DOCS_VERSION", "main")
language = "en"
root_doc = "index"
source_suffix = {".md": "markdown"}
exclude_patterns = ["_build", ".DS_Store"]
templates_path = ["_templates"]
html_static_path = ["_static"]
html_css_files = ["custom.css"]
html_sidebars = {"**": ["global-nav.html"]}

extensions = [
    "myst_parser",
    "sphinx.ext.mathjax",
    "sphinx.ext.githubpages",
    "sphinx_copybutton",
    "sphinx_reredirects",
]
myst_enable_extensions = ["colon_fence", "dollarmath", "amsmath", "deflist"]
myst_heading_anchors = 4
nitpicky = True

html_theme = "pydata_sphinx_theme"
html_title = "MotorFit"
html_baseurl = f"https://motorfit.github.io/{docs_version}/"
html_copy_source = False
html_show_sourcelink = False
html_theme_options = {
    "logo": {"text": "MotorFit"},
    "navbar_start": ["navbar-logo", "version-switcher"],
    "navbar_center": [],
    "switcher": {"json_url": "/versions.json", "version_match": docs_version},
    # The publisher creates this manifest after building; local previews get one below.
    "check_switcher": False,
    "show_nav_level": 2,
    "show_toc_level": 2,
    "navigation_with_keys": True,
    "icon_links": [
        {
            "name": "GitHub",
            "url": "https://github.com/motorfit/motorfit",
            "icon": "fa-brands fa-github",
        }
    ],
}
html_context = {"default_mode": "light"}
copybutton_prompt_text = r"\$ |>>> |\.\.\. "
copybutton_prompt_is_regexp = True

# Compatibility redirects for the original handbook URLs.
redirects = {
    "quickstart": "getting-started/quickstart.html",
    "workflow": "getting-started/workflow.html",
    "your-motor": "guide/configuration.html",
    "acquisition": "guide/acquisition.html",
    "effort-motors": "reference/motors.html",
    "guide/effort-control": "../reference/motors.html",
    "bam-identification": "guide/identification.html",
    "validation": "guide/validation.html",
    "motors": "reference/motors.html",
    "trajectories": "reference/trajectories.html",
    "environments": "reference/backends.html",
    "protocol-references": "reference/protocols.html",
    "architecture": "development/architecture.html",
    "repository": "development/contributing.html",
    "documentation": "development/contributing.html",
    "fixture-masses": "case-studies/rs05-fixture.html",
    "limitations": "case-studies/rs05-findings.html",
}


def write_preview_versions(app, exception):
    """Make a standalone build usable when served at a local HTTP root."""
    if exception is None and app.builder.format == "html":
        versions = [
            {
                "name": "main (dev)" if docs_version == "main" else docs_version,
                "version": docs_version,
                "url": "/",
            }
        ]
        (Path(app.outdir) / "versions.json").write_text(json.dumps(versions) + "\n")


def setup(app):
    app.connect("build-finished", write_preview_versions)
