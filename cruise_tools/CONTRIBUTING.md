# Contributing to cruise_tools

## Git workflow

This repo uses a lightweight **GitHub Flow** — one long-lived branch (`main`)
plus short-lived feature branches.  There are no release branches; versioning
is handled by tags.

### Branch naming

| Purpose | Pattern | Example |
|---------|---------|---------|
| New feature / tool | `feature/<short-description>` | `feature/ctd-flntu-parser` |
| Bug fix | `fix/<short-description>` | `fix/ctd-oxygen-soc-remap` |
| Documentation | `docs/<short-description>` | `docs/anchor-survey-readme` |
| Dependency / config | `chore/<short-description>` | `chore/bump-pandas-3` |

### Day-to-day workflow

```bash
# 1. Start from a fresh main
git checkout main
git pull origin main

# 2. Create your branch
git checkout -b feature/my-new-thing

# 3. Work, committing in logical units (see commit style below)
git add -p          # stage hunks, not whole files
git commit

# 4. Keep up to date with main (rebase, not merge)
git fetch origin
git rebase origin/main

# 5. Push and open a PR
git push -u origin feature/my-new-thing
# → open PR on GitHub targeting main
```

### Commit message style

Follow the **Conventional Commits** convention:
```
<type>(<scope>): <short summary>

[optional body]

[optional footer]
```

**Types:**
- `feat` — new capability
- `fix` — bug fix
- `docs` — documentation only
- `test` — add or fix tests
- `chore` — dependency bumps, CI config, tooling
- `refactor` — internal restructure, no behaviour change

**Scopes** match sub-package names: `ctd`, `anchor_survey`, `common`

**Examples:**
```
feat(ctd): add FLNTU characterisation sheet parser
fix(ctd): correct oxygen Soc coefficient remapping
docs(anchor_survey): update README installation steps
test(ctd): add XMLCONParser minimal-XML smoke test
chore: bump pandas requirement to >=2.2
```

### Pull request checklist

Before requesting review:

- [ ] Branch is rebased on latest `main` (no merge commits)
- [ ] `pytest <sub-package>/` passes locally
- [ ] New public functions have docstrings
- [ ] `CHANGELOG.md` updated under `[Unreleased]`
- [ ] Sub-package `version` bumped in `pyproject.toml` if behaviour changed

### Merging

- Use **squash merge** for small/single-commit branches — keeps `main` clean
- Use **rebase merge** for multi-commit branches where commit history is meaningful
- Never merge with a merge commit (no "Merge branch X into main")

### Tagging a release

```bash
# Bump the version in the relevant pyproject.toml, commit, then:
git tag -a ctd-v0.2.0 -m "cruise-tools-ctd 0.2.0"
git push origin ctd-v0.2.0
```

Tag format: `<sub-package>-v<semver>` so tags are unambiguous in a monorepo.

---

## Environment setup

```bash
git clone https://github.com/WHOIGit/cruise_tools.git
cd cruise_tools
conda env create -f environment.yml
conda activate cruise-tools
```

This installs all sub-packages in editable mode — changes to source files
take effect immediately.

## Running tests

```bash
# All sub-packages from repo root
pytest ctd/ anchor_survey/

# One sub-package only
pytest anchor_survey/

# With coverage
pytest ctd/ --cov=cruise_tools.ctd --cov-report=term-missing
```

## Code style

- Line length: **100** characters (`flake8 --max-line-length=100`)
- Formatter: **black** (optional but encouraged — `black --line-length 100 .`)
- Type hints encouraged but not required
