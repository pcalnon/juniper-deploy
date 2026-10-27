# AGENTS.md - Juniper Deploy

**Project**: juniper-deploy — Docker Compose Orchestration for Juniper Stack
**Repository**: pcalnon/juniper-deploy
**Author**: Paul Calnon
**License**: MIT License
**Version**: 0.3.0
**Last Updated**: 2026-10-26

---

## Hazards (resident — do not relocate)

Directives whose **non-application destroys work**. Everything else in this file may be demoted to
`docs/REFERENCE.md` under the memory budget; these may not, because a pointer only helps an agent
that already knows to look. Adding a new hazard here is legitimate — ratchet space out of a
reference section in the same PR rather than waiving the budget gate.

- **Nothing is written under `/tmp`** — no script, scratch data, test output or pid file: it is a
  tmpfs aged daily, so a file untouched for ten days is deleted in use or not. Temp files go in the
  repo's gitignored `tmp/`; permanent utilities live in `util/`, single-use ones in `util/ad-hoc/`.
  Full rule: § Script Placement.

## Quick Reference

### Essential Commands

```bash
# === Lifecycle (via Makefile) ===
make up           # Start full stack (all real services, detached)
make demo         # Start demo stack (auto-configured CasCor training)
make dev          # Start dev stack (canopy in demo mode)
make down         # Stop and remove all containers
make restart      # Restart all services

# === Observability ===
make monitor      # Full stack + Prometheus + Grafana

# === Monitoring ===
make health       # Detailed health report for all services
make wait         # Block until all services are healthy (90s timeout)
make status       # Show container status
make ps           # Compact container listing

# === Logs ===
make logs         # Tail all service logs (follow)
make logs-data    # Tail JuniperData logs
make logs-cascor  # Tail JuniperCascor logs
make logs-canopy  # Tail JuniperCanopy logs

# === Build ===
make build          # Build/rebuild all images
make build-no-cache # Full rebuild without cache

# === Shell Access ===
make shell-data     # Shell into JuniperData container
make shell-cascor   # Shell into JuniperCascor container
make shell-canopy   # Shell into JuniperCanopy container

# === Cleanup ===
make clean          # Remove containers, volumes, and local images (interactive)

# === Direct Docker Compose (when Makefile is insufficient) ===
docker compose --profile full config    # Validate compose configuration
docker compose logs -f                  # Follow logs (all profiles)

# === Integration Tests ===
pip install -r requirements-test.txt
bash scripts/wait_for_services.sh       # Poll until services healthy
pytest tests/ -v                        # Run full test suite
bash scripts/test_demo_profile.sh       # Demo profile integration test
bash scripts/test_health_enhanced.sh    # Enhanced health check validation
```

### Service Ports

| Service | Host Binding | Container Port | Health Endpoint | Profile(s) |
|---------|-------------|----------------|-----------------|------------|
| juniper-data | 127.0.0.1:8100 | 8100 | `/v1/health` | full, demo, dev |
| juniper-cascor | 0.0.0.0:8201 | 8200 | `/v1/health` | full, dev |
| juniper-cascor-demo | 0.0.0.0:8201 | 8200 | `/v1/health` | demo |
| juniper-canopy | 0.0.0.0:8050 | 8050 | `/v1/health` | full |
| juniper-canopy-demo | 0.0.0.0:8050 | 8050 | `/v1/health` | demo |
| juniper-canopy-dev | 0.0.0.0:8050 | 8050 | `/v1/health` | dev |
| Prometheus | 127.0.0.1:9090 | 9090 | `/-/healthy` | observability |
| AlertManager | 127.0.0.1:9093 | 9093 | `/-/healthy` | observability |
| Grafana | 127.0.0.1:3000 | 3000 | `/api/health` | observability |
| Redis | *(no host binding)* | 6379 | `redis-cli ping` | full, test |

### Key Files

What each core configuration file, script, test module, observability config, secrets directory, doc and CI workflow is for. Moved to [`docs/REFERENCE.md` § Key Files Reference](docs/REFERENCE.md#key-files-reference) — read it when working on this area.

---

## Project Overview

What the stack orchestrates, the Compose profile matrix, and the service dependency graph. Moved to [`docs/REFERENCE.md` § Project Overview Reference](docs/REFERENCE.md#project-overview-reference) — read it when working on this area.

## Directory Layout

The annotated repository tree, with the purpose of every directory and key file. Moved to [`docs/REFERENCE.md` § Directory Layout Reference](docs/REFERENCE.md#directory-layout-reference) — read it when working on this area.

## Script Placement

**Permanent utilities** live in `util/`. **Single-use / temporary / unfinished scripts** go in `util/ad-hoc/` (create on first use). See [`util/ad-hoc/README.md`](util/ad-hoc/README.md) for the per-script header / lifecycle conventions.

`/tmp/` is **prohibited** as the home for any script that produces, modifies, or analyzes repository content: `/tmp/` is reaped, and scripts placed there are lost (irrecoverable). Its old exception for scratch data was withdrawn on 2026-10-26 (§ Temporary files, below).

This is an ecosystem-wide rule restated in the parent `Juniper/AGENTS.md` "Cross-Project Conventions" section. Motivating incident: irrecoverable loss of `phase4_consolidate.py` and `v2_citation_validate.py` from the juniper-ml requirements-snapshot effort.

### Temporary files: `tmp/`, never `/tmp` (mandatory)

**No file is ever written under `/tmp`** (nor `/var/tmp`) by this repo's scripts, tests, tools, services, sessions
or agents (owner directive, 2026-10-26). On the Linux host `/tmp` is a tmpfs that `systemd-tmpfiles-clean` ages
daily (`q /tmp 1777 root root 10d`): a file untouched for ten days is deleted while still in use, and a reboot
erases the rest. In the week to 2026-10-26 it emptied a live test stack's pid files and venv three times. macOS
ages `/tmp` too.

- This repo's temp root is its gitignored `tmp/`. `TMPDIR` points at the **primary** checkout's (it outlives any
  worktree); a worktree-isolated session writes its own scratch files into its worktree's `tmp/`.
- Sessions get `TMPDIR` from the juniper-ml launcher and a user-level SessionStart hook, so `tempfile`, `mktemp` and
  pytest's `tmp_path` follow it.
- In code: never a `/tmp/...` literal and never `${TMPDIR:-/tmp}`; tests use `tmp_path`; state another process must
  find (pid files, run directories) lives at a fixed path under the primary's `tmp/` or `~/.local/state/`, never one
  derived from `TMPDIR`.
- Out of scope: GitHub-hosted CI runners and a container's own `/tmp` (the Helm charts' `emptyDir` mounts).
- Ecosystem rule and rationale: `juniper-ml/notes/JUNIPER_2026-10-26_JUNIPER-ECOSYSTEM_REPO-TMP-DIRECTORY-CONVENTION.md`.
- **Owner rulings, 2026-10-26** (canonical: the note above): `juniper-check-doc-links` passes `--exclude tmp` and a
  local Docker build's `.dockerignore` lists `tmp/`; pytest does not ignore it (no `norecursedirs`, `--ignore` or
  `collect_ignore` names it). Full-tree repo copies and log-file copies may live there.
  - A script that counts matches with `grep` or `find` chooses its scope deliberately: the repo with its `tmp/`
    excluded, or `tmp/` alone; it searches both only for a stated edge case that needs both. Existing counting
    scripts are to be modified to make that choice explicit, not left to `.gitignore` or a tool's defaults.
  - **Retention.** A file a work arc writes to `tmp/` is kept until it is no longer needed, no work arc (its own
    included) uses it, and it is no longer needed for documentation or reference, and, where needed, until it has
    been archived in an appropriate non-temporary directory. Only then may it be deleted.

---

## Ecosystem Context

Part of the Juniper ecosystem. See the parent directory's `CLAUDE.md` at `/home/pcalnon/Development/python/Juniper/CLAUDE.md` for the full project map, dependency graph, shared conventions, and conda environment details.

---

## Environment Variables

Every environment variable the stack reads, its default, and which service consumes it. Moved to [`docs/REFERENCE.md` § Environment Variable Reference](docs/REFERENCE.md#environment-variable-reference) — read it when working on this area.

## Security Architecture

The stack's trust boundaries, bind posture, and the secret-delivery path. Moved to [`docs/REFERENCE.md` § Security Architecture Reference](docs/REFERENCE.md#security-architecture-reference) — read it when working on this area.

## CI/CD Pipeline

GitHub Actions workflow (`.github/workflows/ci.yml`, v0.2.0):

**Triggers**: push to `main`, `develop`, `feature/**`, `fix/**`; pull requests; manual dispatch

**Jobs**:

| Job | Purpose | Dependencies |
|-----|---------|-------------|
| `pre-commit` | YAML, shell, markdown, Python validation | — |
| `validate-compose` | Compose config validation (full, demo, dev profiles) | pre-commit |
| `docker-integration` | Build dev profile, start services, verify health endpoints (15min timeout) | validate-compose |
| `required-checks` | Quality gate enforcement (all jobs must pass) | all |

**Notes**:

- Multi-repo checkout: CI checks out `juniper-data`, `juniper-cascor`, and `juniper-canopy` as sibling directories (required for `docker compose build`)
- All GitHub Actions are SHA-pinned (checkout@v6.0.2, setup-python@v6.2.0, cache@v5.0.4)
- `docker-compose-check` pre-commit hook is skipped in CI (handled by dedicated `validate-compose` job)

### Sequence-Safety Net (required check; rollout W2, 2026-08-08)

Two workflows port the ecosystem sequence-safety screens (the 2026-07-28 Cursor-PR-flood remediation) into juniper-deploy as the final consumer of the rollout (8th of 8 repos). Both consume the published `juniper-ci-tools>=0.9.0,<0.10.0` package — no inline copy lives in this repo.

| Workflow | Trigger | Role |
|----------|---------|------|
| `.github/workflows/sequence-safety.yml` | `pull_request` | Per-PR AST symbol-loss + docs deletion-magnitude screens over the PR's `base..HEAD`; uploads a `sequence-safety-report` JSON artifact. |
| `.github/workflows/main-verify.yml` | `push: main` | Post-merge, bypass-proof re-screen of the merged range (per-SHA, no-cancel; catch-up base); upserts a stable-title tracking issue on failure. |

**Scope (owner decision, option b):** the symbol screen is scoped to `tests/**/*.py` (the security-wiring tests) and `scripts/**/*.bash` (operational bash); the docs deletion-magnitude screen uses the universal default (`AGENTS.md` + `docs/**/*.md` + `notes/**/*.md`).

**Required, but outside the Quality Gate:** `sequence-safety.yml` publishes **`Sequence Safety`**, a required context in ruleset `juniper-deploy-rules` (id `14715370`), so a red run blocks merge into `main`.
Neither workflow is wired into the `required-checks` Quality Gate (a `needs:` entry can only name a job in the same workflow), so a green Quality Gate does not mean mergeable. `main-verify.yml` runs after the merge and is not a PR status check.
The escape hatches are the `Allow-Symbol-Loss:` / `Allow-Docs-Rewrite:` commit trailers (primary, and the only waiver `main-verify.yml` honours; on a squash merge, carry them into the squash commit message) and the `allow-symbol-loss` / `docs-rewrite` PR labels (WARN-only downgrade, which greens the required check for that PR).
Live list: `gh api repos/pcalnon/juniper-deploy/rulesets/14715370 --jq '.rules[] | select(.type=="required_status_checks") | .parameters.required_status_checks[].context'`.

---

### PR base-branch guard (required check)

`.github/workflows/pr-base-branch-guard.yml` fails any PR whose base branch is not the
default branch. Its job name -- **`Guard PR base branch`** -- is a **required status check**
in this repo's ruleset, so renaming the job or deleting the file makes `main` unmergeable
until the context is un-required first.

**What it protects against.** A PR based on another feature branch can squash-merge into
that branch, stranding its content off `main` behind a green **MERGED** badge. It has
happened three times in this ecosystem (`juniper-recurrence#7`/`#8`, `juniper-canopy#365`).

**Why it matters more than it looks.** Both rulesets here are scoped to `~DEFAULT_BRANCH`, so
a PR whose base is a feature branch is governed by **no ruleset at all** -- it has zero
required status checks and merges clean with nothing having run:

```bash
gh api repos/pcalnon/<repo>/rules/branches/feature%2Fanything --jq length   # -> 0
gh api repos/pcalnon/<repo>/rules/branches/main               --jq length   # -> 9
```

This workflow carries no `branches:` filter, so it is the **only** check that runs on such a
PR. It cannot block the merge there -- no ruleset applies -- but it turns a silent merge into
a visibly red one.

**If it fails.** Re-open the work against the default branch. The house practice is
**close and re-open** a fresh PR titled `[retarget #NNN]`. Retargeting in place is *not*
sufficient on its own: every `ci*.yml` here uses the default `pull_request` types
`[opened, synchronize, reopened]`, which exclude `edited`, so a retarget re-runs this guard
and nothing else -- the PR stays blocked on its other required contexts until a push or a
close/re-open.

**`stacked-pr` label.** Silences this guard for a deliberate stack. It does **not** make the
PR mergeable into `main`, and it does **not** re-land the stack -- do that separately.

Rollout and rationale: [juniper-ml#434](https://github.com/pcalnon/juniper-ml/issues/434).

## Testing

Per-suite detail: what each test file covers and the marker it carries. Moved to [`docs/REFERENCE.md` § Testing Reference](docs/REFERENCE.md#testing-reference) — read it when working on this area.

## Documentation

The documentation set, what each document is for, and where it lives. Moved to [`docs/REFERENCE.md` § Documentation Reference](docs/REFERENCE.md#documentation-reference) — read it when working on this area.

## Worktree Procedures (Mandatory — Task Isolation)

> **OPERATING INSTRUCTION**: All feature, bugfix, and task work SHOULD use git worktrees for isolation. Worktrees keep the main working directory on the default branch while task work proceeds in a separate checkout.

### What This Is

Git worktrees allow multiple branches of a repository to be checked out simultaneously in separate directories. For the Juniper ecosystem, all worktrees are centralized in **`/home/pcalnon/Development/python/Juniper/worktrees/`** using a standardized naming convention.

The full setup and cleanup procedures are defined in:

- **`notes/WORKTREE_SETUP_PROCEDURE.md`** — Creating a worktree for a new task
- **`notes/WORKTREE_CLEANUP_PROCEDURE_V2.md`** — Merging, removing, and pushing after task completion (V2 — fixes CWD-trap bug)

Read the appropriate file when starting or completing a task.

### Worktree Directory Naming

Format: `<repo-name>--<branch-name>--<YYYYMMDD-HHMM>--<short-hash>`

Example: `juniper-deploy--feature--add-monitoring--20260225-1430--50700461`

- Slashes in branch names are replaced with `--`
- All worktrees reside in `/home/pcalnon/Development/python/Juniper/worktrees/`

### When to Use Worktrees

| Scenario | Use Worktree? |
| -------- | ------------- |
| Feature development (new feature branch) | **Yes** |
| Bug fix requiring a dedicated branch | **Yes** |
| Quick single-file documentation fix on main | No |
| Exploratory work that may be discarded | **Yes** |
| Hotfix requiring immediate merge | **Yes** |

### Quick Reference

**Setup** (full procedure in `notes/WORKTREE_SETUP_PROCEDURE.md`):

```bash
cd /home/pcalnon/Development/python/Juniper/juniper-deploy
git fetch origin && git checkout main && git pull origin main
BRANCH_NAME="feature/my-task"
git branch "$BRANCH_NAME" main
REPO_NAME=$(basename "$(pwd)")
SAFE_BRANCH=$(echo "$BRANCH_NAME" | sed 's|/|--|g')
WORKTREE_DIR="/home/pcalnon/Development/python/Juniper/worktrees/${REPO_NAME}--${SAFE_BRANCH}--$(date +%Y%m%d-%H%M)--$(git rev-parse --short=8 HEAD)"
git worktree add "$WORKTREE_DIR" "$BRANCH_NAME"
cd "$WORKTREE_DIR"
```

**Cleanup** (full procedure in `notes/WORKTREE_CLEANUP_PROCEDURE_V2.md`):

```bash
# Phase 1: Push current work
cd "$OLD_WORKTREE_DIR" && git push origin "$OLD_BRANCH"
# Phase 2: Create new worktree BEFORE removing old (prevents CWD-trap)
git fetch origin
git worktree add "$NEW_WORKTREE_DIR" -b "$NEW_BRANCH" origin/main
cd "$NEW_WORKTREE_DIR"
# Phase 3: Create PR (do NOT merge directly to main)
gh pr create --base main --head "$OLD_BRANCH" --title "<title>" --body "<body>"
# Phase 4: Cleanup
git worktree remove "$OLD_WORKTREE_DIR"
git branch -d "$OLD_BRANCH"
git worktree prune
```

### Rules

- **Centralized location**: All worktrees go in `/home/pcalnon/Development/python/Juniper/worktrees/`. Never create worktrees inside the repo directory.
- **Clean before you start**: Ensure the main working directory is clean before creating a worktree.
- **Push before you merge**: Always push the working branch to remote before merging (backup).
- **Prune after cleanup**: Run `git worktree prune` after removing a worktree to clean metadata.
- **Do not leave stale worktrees**: Clean up worktrees promptly after merging.

---

## Thread Handoff (Mandatory — Replaces Thread Compaction)

> **CRITICAL OPERATING INSTRUCTION**: Thread handoff MUST be performed instead of thread compaction. This section defines mandatory behavior that overrides Claude Code's default compaction process.

### What This Is

When a long-running conversation approaches context limits, Claude Code normally performs **thread compaction** — summarizing prior context to free token capacity. This introduces information loss. Instead, Claude Code instances working on this project MUST perform a **proactive thread handoff**: transferring a curated, high-signal summary to a fresh thread with full context capacity.

The full handoff protocol is defined in **`notes/THREAD_HANDOFF_PROCEDURE.md`**. Read that file when a handoff is triggered.

### When to Trigger a Handoff

**Automatic trigger (pre-compaction threshold):** Initiate a thread handoff when token utilization reaches **95% to 99%** of the level at which thread compaction would normally be triggered.

**Additional triggers**:

| Condition | Indicator |
| --------- | --------- |
| **Context saturation** | Thread has performed 15+ tool calls or edited 5+ files |
| **Phase boundary** | A logical phase of work is complete |
| **Degraded recall** | Re-reading a file already read, or re-asking a resolved question |
| **Multi-module transition** | Moving between major components |
| **User request** | User says "hand off", "new thread", or similar |

**Do NOT handoff** when:

- The task is nearly complete (< 2 remaining steps)
- The current thread is still sharp and producing correct output
- The work is tightly coupled and splitting would lose critical in-flight state

### How to Execute a Handoff

1. **Checkpoint**: Inventory what was done, what remains, what was discovered, and what files are in play
2. **Compose the handoff goal**: Write a concise, actionable summary (see templates in `notes/THREAD_HANDOFF_PROCEDURE.md`)
3. **Present to user**: Output the handoff goal to the user and recommend starting a new thread with that goal as the initial prompt
4. **Include verification commands**: Always specify how the new thread should verify its starting state
5. **State git status**: Mention branch, staged files, and any uncommitted work

### Rules

- **This is not optional.** Every Claude Code instance on this project must follow these rules.
- **Handoff early, not late.** A handoff at 70% context usage is better than compaction at 95%.
- **Do not duplicate CLAUDE.md content** in the handoff goal — the new thread reads CLAUDE.md automatically.
- **Be specific** in the handoff goal: include file paths, decisions made, and test status.
