# Releasing Portmint Pulse

This project ships two automated workflows:

- **`pages.yml`** — on every push to `main`, builds the static demo and deploys it to GitHub Pages.
- **`publish.yml`** — when you publish a GitHub Release, builds and uploads the package to PyPI using
  **Trusted Publishing** (OIDC, no stored token).

## One-time setup

### GitHub Pages (for the live demo)

Repo **Settings → Pages → Build and deployment → Source: GitHub Actions**. After that, every push to
`main` redeploys the demo to `https://colelevy08.github.io/portmint-pulse/`.

### PyPI Trusted Publishing (for `pip install portmint-pulse`)

1. Create the project owner on [PyPI](https://pypi.org) (log in / register).
2. Go to **Your projects → Publishing → Add a pending publisher** (or the project's *Publishing*
   settings once it exists) and add a **GitHub Actions** trusted publisher:
   - Owner: `colelevy08`
   - Repository: `portmint-pulse`
   - Workflow filename: `publish.yml`
   - Environment name: `pypi`
3. In this repo, **Settings → Environments → New environment → `pypi`** (no secrets needed; the
   environment just scopes the OIDC trust).
4. **Enable the publish job:** `gh variable set PYPI_READY --body true` (or Settings → Secrets and
   variables → Actions → Variables → New variable `PYPI_READY` = `true`). Until this is set, the
   `publish.yml` job **skips** (a neutral result, not a red failure) so cutting releases before PyPI is
   configured doesn't litter the Actions tab.

No API tokens are ever stored — PyPI verifies the GitHub OIDC identity at publish time.

## Cutting a release

1. Bump the version in `portmint_pulse/__init__.py` (single source of truth) and update `CHANGELOG.md`.
2. Commit, tag, and push:
   ```bash
   git commit -am "release: vX.Y.Z"
   git tag vX.Y.Z
   git push && git push --tags
   ```
3. Create a **GitHub Release** for that tag. Publishing the release triggers `publish.yml` → PyPI.

Versioning follows [SemVer](https://semver.org/).
