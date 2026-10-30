# Build and maintain the documentation

The handbook uses **Sphinx**, **MyST Markdown** and the **PyData Sphinx Theme**.
Its canonical sources live in `docs/` in the private `motorfit/motorfit` repository.
The published site is [motorfit.github.io](https://motorfit.github.io/).

## Build locally

From the repository root:

```bash
uv run --frozen --only-group docs sphinx-build \
  -W --keep-going -b html -d outputs/docs-doctrees docs outputs/docs
python3 -m http.server 8000 --directory outputs/docs
```

Open `http://localhost:8000/`. The docs dependency group is independent of the
motor and simulation runtimes; building the handbook does not import MotorFit or
require the BAM submodule, a motor, or a GPU. Build warnings fail the command so
missing pages, images and unresolved references are caught before publication.

## Edit pages

Write Markdown in `docs/`, add new pages to the appropriate toctree in `index.md`,
and use relative links between handbook pages. MyST adds directives and math while
retaining Markdown for ordinary prose, lists, tables and code blocks.

Links to repository source files use their full GitHub URL. These links require
repository access; handbook pages remain publicly readable. Keep source references
separate from handbook navigation so they resolve correctly on the website.

English is the default for technical guides and new pages. `README.zh-CN.md`
provides the Chinese introduction and entry points; update both README files when
setup commands or project scope change. Recorded evidence keeps its original
language and bytes.

## Publish

The `Documentation` GitHub Actions workflow strictly builds the handbook on pull
requests and pushes to `main`, then saves a `motorfit-docs` artifact. It can also
be run manually. The public `motorfit/motorfit.github.io` repository serves its
`main` branch through GitHub Pages.

After committing and pushing documentation changes, publish from a local checkout:

```bash
bash scripts/publish_docs.sh
```

The script requires `uv` and SSH write access to the site repository. It refuses
uncommitted documentation inputs, rebuilds in a temporary directory, and pushes
only the rendered files as an ordinary commit. Each publication records the source
commit. GitHub Pages deploys the resulting site commit automatically.

The organization disables deploy keys, so publication uses the maintainer's existing
local Git credentials. CI does not hold a cross-repository deployment credential.

Only built documentation and its static assets are published. Experiment archives,
recordings, source code and environments are not copied to the site repository.
Generated HTML belongs in ignored `outputs/docs/` locally and in the deployment
repository remotely; never stage it in the source repository. See the
[tracking policy](repository.md).
