"""Build the public handbook without importing MotorFit or hardware backends."""

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
metadata = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]

project = "MotorFit"
author = "MotorFit contributors"
copyright = "2026, MotorFit contributors"
release = metadata["version"]
version = release
language = "en"
root_doc = "index"
source_suffix = {".md": "markdown"}
exclude_patterns = ["_build", ".DS_Store"]
templates_path = ["_templates"]
html_sidebars = {"**": ["global-nav.html"]}

extensions = [
    "myst_parser",
    "sphinx.ext.mathjax",
    "sphinx.ext.githubpages",
    "sphinx_copybutton",
]
myst_enable_extensions = ["colon_fence", "dollarmath", "amsmath", "deflist"]
myst_heading_anchors = 4
nitpicky = True

html_theme = "pydata_sphinx_theme"
html_title = "MotorFit"
html_baseurl = "https://motorfit.github.io/"
html_copy_source = False
html_show_sourcelink = False
html_theme_options = {
    "logo": {"text": "MotorFit"},
    "navbar_center": [],
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
