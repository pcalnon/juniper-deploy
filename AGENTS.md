# AGENTS.md - Juniper Deploy

**Project**: juniper-deploy — Docker Compose Orchestration for Juniper Stack
**Version**: 0.1.0
**License**: MIT License
**Author**: Paul Calnon
**Last Updated**: 2026-02-25

---

## Quick Reference

### Essential Commands

```bash
# Validate compose configuration
docker compose --profile full config

# Start full stack (all real services)
make up    # or: docker compose --profile full up -d

# Start demo stack (auto-configured CasCor training)
make demo  # or: docker compose --profile demo up -d

# Start dev stack (canopy in demo mode)
make dev   # or: docker compose --profile dev up -d

# View logs
docker compose logs -f

# Stop all services
make down

# Check service health
docker compose ps

# Run demo integration test
bash scripts/test_demo_profile.sh

# Run integration tests
pip install -r requirements-test.txt
bash scripts/wait_for_services.sh
pytest tests/ -v
```

### Service Ports

| Service | Default Port | Health Endpoint |
|---------|-------------|-----------------|
| juniper-data | 8100 | `/v1/health` |
| juniper-cascor | 8200 | `/v1/health` |
| juniper-canopy | 8050 | `/v1/health` |

### Key Files

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Service orchestration with profiles (`full`, `demo`, `dev`) |
| `.env.example` | All configurable environment variables |
| `.env.demo` | Demo profile environment overrides |
| `scripts/wait_for_services.sh` | Polls health endpoints before tests |
| `scripts/test_demo_profile.sh` | Demo profile integration test script |
| `tests/conftest.py` | Shared fixtures (configurable via `JUNIPER_TEST_*` env vars) |
| `tests/test_health.py` | Health endpoint + schema validation tests |
| `tests/test_data_service.py` | Dataset lifecycle integration tests |
| `tests/test_full_stack.py` | Cross-service end-to-end tests |
| `README.md` | Quickstart, profiles, service discovery, env var docs |

---

## Project Overview

`juniper-deploy` orchestrates the full Juniper stack via Docker Compose. It manages service dependencies, health checks, and environment variable wiring for the three core services: JuniperData, JuniperCascor, and JuniperCanopy.

### Service Dependency Graph

```
juniper-canopy (8050)
  └── depends_on: juniper-cascor (healthy), juniper-data (healthy)

juniper-cascor (8200)
  └── depends_on: juniper-data (healthy)

juniper-data (8100)
  └── no dependencies
```

---

## Ecosystem Context

Part of the Juniper ecosystem. See the parent directory's `CLAUDE.md` at `/home/pcalnon/Development/python/Juniper/CLAUDE.md` for the full project map, dependency graph, shared conventions, and conda environment details.

### Environment Variables

All values use `${VAR:-default}` substitution in `docker-compose.yml`. Copy `.env.example` to `.env` to override.

| Variable | Service | Default |
|----------|---------|---------|
| `JUNIPER_DATA_HOST` | juniper-data | `0.0.0.0` |
| `JUNIPER_DATA_PORT` | juniper-data | `8100` |
| `JUNIPER_DATA_LOG_LEVEL` | juniper-data | `INFO` |
| `CASCOR_HOST` | juniper-cascor | `0.0.0.0` |
| `CASCOR_PORT` | juniper-cascor | `8200` |
| `CASCOR_LOG_LEVEL` | juniper-cascor | `INFO` |
| `CANOPY_HOST` | juniper-canopy | `0.0.0.0` |
| `CANOPY_PORT` | juniper-canopy | `8050` |
| `JUNIPER_DATA_URL` | juniper-cascor, juniper-canopy | `http://juniper-data:8100` |
| `CASCOR_SERVICE_URL` | juniper-canopy | `http://juniper-cascor:8200` |
| `JUNIPER_DATA_API_KEYS` | juniper-data | *(unset — auth disabled)* |
| `JUNIPER_CASCOR_API_KEYS` | juniper-cascor | *(unset — auth disabled)* |
| `CANOPY_API_KEY` | juniper-canopy | *(unset — auth disabled)* |
| `JUNIPER_CASCOR_RATE_LIMIT_ENABLED` | juniper-cascor | `false` |
| `JUNIPER_CASCOR_RATE_LIMIT_REQUESTS_PER_MINUTE` | juniper-cascor | `60` |
| `CANOPY_RATE_LIMIT_ENABLED` | juniper-canopy | `false` |
| `CANOPY_RATE_LIMIT_REQUESTS_PER_MINUTE` | juniper-canopy | `60` |
| `JUNIPER_DATA_LOG_FORMAT` | juniper-data | `text` |
| `JUNIPER_DATA_SENTRY_DSN` | juniper-data | *(unset)* |
| `JUNIPER_DATA_METRICS_ENABLED` | juniper-data | `false` |
| `JUNIPER_CASCOR_LOG_FORMAT` | juniper-cascor | `text` |
| `JUNIPER_CASCOR_SENTRY_DSN` | juniper-cascor | *(unset)* |
| `JUNIPER_CASCOR_METRICS_ENABLED` | juniper-cascor | `false` |
| `CANOPY_LOG_FORMAT` | juniper-canopy | `text` |
| `CANOPY_SENTRY_DSN` | juniper-canopy | *(unset)* |
| `CANOPY_METRICS_ENABLED` | juniper-canopy | `false` |
| `GRAFANA_ADMIN_PASSWORD` | grafana | `admin` |
| `JUNIPER_CASCOR_AUTO_START` | juniper-cascor-demo | `true` |
| `JUNIPER_CASCOR_AUTO_DATASET` | juniper-cascor-demo | `spiral` |
| `JUNIPER_CASCOR_AUTO_DATASET_PARAMS` | juniper-cascor-demo | JSON params |
| `JUNIPER_CASCOR_AUTO_NETWORK` | juniper-cascor-demo | JSON config |
| `JUNIPER_CASCOR_AUTO_TRAIN_EPOCHS` | juniper-cascor-demo | `500` |
| `CASCOR_DEMO_MODE` | juniper-canopy-dev | `1` |

---

## Worktree Procedures (Mandatory — Task Isolation)

> **OPERATING INSTRUCTION**: All feature, bugfix, and task work SHOULD use git worktrees for isolation. Worktrees keep the main working directory on the default branch while task work proceeds in a separate checkout.

### What This Is

Git worktrees allow multiple branches of a repository to be checked out simultaneously in separate directories. For the Juniper ecosystem, all worktrees are centralized in **`/home/pcalnon/Development/python/Juniper/worktrees/`** using a standardized naming convention.

The full setup and cleanup procedures are defined in:
- **`notes/WORKTREE_SETUP_PROCEDURE.md`** — Creating a worktree for a new task
- **`notes/WORKTREE_CLEANUP_PROCEDURE.md`** — Merging, removing, and pushing after task completion

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

**Cleanup** (full procedure in `notes/WORKTREE_CLEANUP_PROCEDURE.md`):
```bash
cd "$WORKTREE_DIR" && git push origin "$BRANCH_NAME"
cd /home/pcalnon/Development/python/Juniper/juniper-deploy
git checkout main && git pull origin main
git merge "$BRANCH_NAME"
git push origin main
git worktree remove "$WORKTREE_DIR"
git branch -d "$BRANCH_NAME"
git push origin --delete "$BRANCH_NAME"
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
