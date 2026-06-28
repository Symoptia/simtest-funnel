# Maintainer Guide

This document covers secrets management, registry setup, release procedures, and
troubleshooting for the **simtest-funnel** repository.

---

## Required GitHub Secrets

All secrets must be configured in the repository settings at
`Settings → Secrets and variables → Actions → Repository secrets`.

### Registry Summary

| Registry | URL | Secret Name | Package / Project | Notes |
|----------|-----|-------------|-------------------|-------|
| PyPI | https://pypi.org | `PYPI_API_TOKEN` | `simtest-funnel` | Project-scoped token |
| crates.io | https://crates.io | `CARGO_REGISTRY_TOKEN` | `simtest-funnel-core` | API token |
| NPM | https://www.npmjs.com | `NPM_TOKEN` | `@simtest-js/funnel` | Automation token with org publish |
| Cloudflare Pages | https://dash.cloudflare.com | `CLOUDFLARE_API_TOKEN` | `simtest-funnel` | Pages Edit API token |
| Cloudflare | https://dash.cloudflare.com | `CLOUDFLARE_ACCOUNT_ID` | — | Account ID |
| GitHub | https://github.com | `GH_TOKEN` | — | PAT with `repo` + `workflow` scopes |

### PYPI_API_TOKEN

- **Purpose:** Publish Python wheel to PyPI as `simtest-funnel`.
- **Source:** https://pypi.org/manage/account/token/ → create project-scoped token for `simtest-funnel`.
- **Set:**
  ```bash
  gh secret set PYPI_API_TOKEN --body "pypi-..." --repo Symoptia/simtest-funnel
  ```
- **Verify:**
  ```bash
  gh secret list --repo Symoptia/simtest-funnel | grep PYPI_API_TOKEN
  ```

### CARGO_REGISTRY_TOKEN

- **Purpose:** Publish Rust crate to crates.io as `simtest-funnel-core`.
- **Source:** https://crates.io/settings/tokens → create a token with publish scope.
- **Set:**
  ```bash
  gh secret set CARGO_REGISTRY_TOKEN --body "..." --repo Symoptia/simtest-funnel
  ```
- **Verify:**
  ```bash
  gh secret list --repo Symoptia/simtest-funnel | grep CARGO_REGISTRY_TOKEN
  ```

### NPM_TOKEN

- **Purpose:** Publish `@simtest-js/funnel` to NPM under the `@simtest-js` org.
- **Source:** https://www.npmjs.com/settings → Access Tokens → create automation token
  with publish permissions for `@simtest-js/` scope.
- **Set:**
  ```bash
  gh secret set NPM_TOKEN --body "npm_..." --repo Symoptia/simtest-funnel
  ```
- **Verify:**
  ```bash
  gh secret list --repo Symoptia/simtest-funnel | grep NPM_TOKEN
  ```

### CLOUDFLARE_API_TOKEN

- **Purpose:** Deploy documentation to Cloudflare Pages (`simtest-funnel` project).
- **Source:** https://dash.cloudflare.com/profile/api-tokens → create token with
  `Cloudflare Pages:Edit` permission.
- **Set:**
  ```bash
  gh secret set CLOUDFLARE_API_TOKEN --body "..." --repo Symoptia/simtest-funnel
  ```
- **Verify:**
  ```bash
  gh secret list --repo Symoptia/simtest-funnel | grep CLOUDFLARE_API_TOKEN
  ```

### CLOUDFLARE_ACCOUNT_ID

- **Purpose:** Identify the Cloudflare account for Pages deployment.
- **Source:** https://dash.cloudflare.com → account overview → Account ID (right sidebar).
- **Set:**
  ```bash
  gh secret set CLOUDFLARE_ACCOUNT_ID --body "..." --repo Symoptia/simtest-funnel
  ```
- **Verify:**
  ```bash
  gh secret list --repo Symoptia/simtest-funnel | grep CLOUDFLARE_ACCOUNT_ID
  ```

### GH_TOKEN

- **Purpose:** GitHub PAT used by semantic-release to create releases, push tags,
  and commit version bumps.
- **Source:** https://github.com/settings/tokens → Fine-grained or classic PAT with
  `repo` and `workflow` scopes.
- **Set:**
  ```bash
  gh secret set GH_TOKEN --body "github_pat_..." --repo Symoptia/simtest-funnel
  ```
- **Verify:**
  ```bash
  gh secret list --repo Symoptia/simtest-funnel | grep GH_TOKEN
  ```

---

## `.env` File Pattern

- `.env` is git-ignored and contains local credentials.
- `.env.example` documents the required variable names with placeholder values.
- **Never commit `.env`.**
- To sync `.env` values to GitHub Secrets:
  ```bash
  bash scripts/setup-gh-secrets.sh
  ```

---

## Secrets Verification

Run at any time to validate both local `.env` and GitHub Secrets:

```bash
make check-secrets
```

This calls `scripts/check-secrets.sh` which checks all 6 required variables.

---

## Cloudflare Pages Setup

Before the first release, create the Cloudflare Pages project:

```bash
bash scripts/cloudflare-setup.sh
```

This is idempotent — safe to run multiple times.

---

## Release Procedures

### Pre-release (Beta)

1. Ensure all tests pass: `make test && make lint`
2. Push to the `beta` branch:
   ```bash
   git push origin HEAD:beta
   ```
3. Monitor the release workflow:
   ```bash
   gh run list --repo Symoptia/simtest-funnel --branch beta --limit 1
   gh run watch <RUN_ID> --repo Symoptia/simtest-funnel
   ```
4. Verify the pre-release tag (e.g., `v0.1.0-beta.1`):
   ```bash
   gh release list --repo Symoptia/simtest-funnel
   ```

### Stable Release

1. Merge `beta` (or feature branch) into `main`:
   ```bash
   git checkout main && git merge beta && git push origin main
   ```
2. The release workflow will automatically:
   - Determine the version bump from Conventional Commits
   - Update CHANGELOG.md, Cargo.toml, pyproject.toml, package.json
   - Create a GitHub Release
   - Publish to PyPI, crates.io, NPM
   - Deploy docs to Cloudflare Pages

---

## Secrets Rotation

Rotate all secrets every **90 days**. Procedure:

1. Generate new tokens from each registry's dashboard.
2. Update `.env` locally.
3. Run `bash scripts/setup-gh-secrets.sh` to sync to GitHub.
4. Verify: `make check-secrets`.
5. Trigger a beta release to confirm the new tokens work.

---

## Troubleshooting

### PyPI publish fails

- Verify token scope: must be project-scoped for `simtest-funnel`.
- Check token hasn't expired: re-create at https://pypi.org/manage/account/token/.
- Ensure the package name isn't taken by another owner.

### crates.io publish fails

- Verify token has publish scope.
- Ensure `simtest-funnel-core` crate name is available (first publish claims it).
- Check `Cargo.toml` version isn't already published.

### NPM publish fails

- Verify token is an automation token (not granular) with publish scope.
- Ensure `@simtest-js` org exists and your token has permissions.
- Check the `packages/sdk/package.json` version hasn't been published yet.

### Cloudflare Pages deploy fails

- Verify `CLOUDFLARE_API_TOKEN` has `Cloudflare Pages:Edit` permission.
- Verify `CLOUDFLARE_ACCOUNT_ID` matches the account with the project.
- Run `bash scripts/cloudflare-setup.sh` to ensure the project exists.

### GitHub Release fails

- Verify `GH_TOKEN` has `repo` + `workflow` scopes.
- Check semantic-release can access the repository (token not expired).
- Ensure commit messages follow Conventional Commits format.

### CI container image not found

- The CI jobs use `ghcr.io/symoptia/simtest-funnel-devcontainer:latest`.
- If the image doesn't exist, trigger the `Build Devcontainer` workflow manually:
  ```bash
  gh workflow run build-devcontainer.yml --repo Symoptia/simtest-funnel
  ```
