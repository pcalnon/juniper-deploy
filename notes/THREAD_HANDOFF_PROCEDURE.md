# Thread Handoff Procedure

**Purpose**: Preserve context fidelity during long-running Claude Code sessions by proactively handing off to a new thread before context compaction degrades output quality.

**Project**: juniper-deploy
**Last Updated**: 2026-03-02

---

## Why Handoff Over Compaction

Thread compaction summarizes prior context to free token capacity. This introduces **information loss** — subtle details about decisions made, edge cases discovered, partial progress, and the reasoning behind specific implementation choices get compressed or dropped. For work on juniper-deploy (e.g., Compose profile changes, service health check updates, integration test modifications, environment variable wiring), this degradation can cause:

- Repeated mistakes the thread already resolved
- Inconsistent configuration mid-task
- Loss of discovered constraints or gotchas
- Re-reading files that were already understood

A **proactive handoff** transfers a curated, high-signal summary to a fresh thread with full context capacity, preserving the critical information while discarding the noise.

---

## When to Initiate a Handoff

Trigger a handoff when **any** of the following conditions are met:

| Condition                   | Indicator                                                                                                                   |
| --------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| **Context saturation**      | Thread has performed 15+ tool calls or edited 5+ files                                                                      |
| **Phase boundary**          | A logical phase of work is complete (e.g., planning done → implementation starting; implementation done → testing starting) |
| **Degraded recall**         | The agent re-reads a file it already read, or asks a question it already resolved                                           |
| **Multi-module transition** | Moving from one major component to another (e.g., `docker-compose.yml` → `scripts/` → `tests/`)                             |
| **User request**            | User says "hand off", "new thread", "continue in a fresh thread", or similar                                                |

**Do NOT handoff** when:

- The task is nearly complete (< 2 remaining steps)
- The current thread is still sharp and producing correct output
- The work is tightly coupled and splitting would lose critical in-flight state

---

## Handoff Protocol

### Step 1: Checkpoint Current State

Before initiating the handoff, mentally inventory:

1. **What was the original task?** (user's request, verbatim or paraphrased)
2. **What has been completed?** (files created, files edited, tests passed/failed)
3. **What remains?** (specific next steps, not vague summaries)
4. **What was discovered?** (gotchas, constraints, decisions, rejected approaches)
5. **What files are in play?** (paths of files read, modified, or relevant)

### Step 2: Compose the Handoff Goal

Write a **concise, actionable** goal for the new thread. Structure it as:

```bash
Continue [TASK DESCRIPTION].

Completed so far:
- [Concrete item 1]
- [Concrete item 2]

Remaining work:
- [Specific next step 1]
- [Specific next step 2]

Key context:
- [Important discovery or constraint]
- [File X was modified to do Y]
- [Approach Z was rejected because...]
```

**Rules for the goal**:

- **Be specific**: "Add Prometheus scrape config for juniper-cascor" not "finish the monitoring work"
- **Include file paths**: The new thread doesn't know what you've been looking at
- **State decisions made**: So the new thread doesn't re-litigate them
- **Mention test status**: If tests were run, state pass/fail counts
- **Keep it under ~500 words**: Dense signal, no filler

### Step 3: Execute the Handoff

Present the composed handoff goal to the user and recommend starting a new thread with it as the initial prompt. If the `handoff()` tool is available:

```bash
handoff(
    goal="<composed goal from Step 2>",
    follow=true
)
```

- Set `follow=true` when the current thread should stop and work continues in the new thread (the common case).
- Set `follow=false` only if the current thread has independent remaining work (rare).

---

## Handoff Goal Templates

### Template: Implementation In Progress

```bash
Continue implementing [FEATURE] in juniper-deploy.

Completed:
- Modified [file1] with [description]
- Added tests in [test_file] (X/Y passing)

Remaining:
- Implement [specific service/profile change]
- Add tests for [specific behavior]
- Validate with: docker compose --profile full config

Key context:
- Using [pattern/approach] because [reason]
- [File X] has a constraint: [detail]
- Validate config: docker compose --profile full config
- Run tests: pytest tests/ -v
```

### Template: Debugging Session

```bash
Continue debugging [ISSUE DESCRIPTION] in juniper-deploy.

Findings so far:
- Root cause is likely in [file:line] because [evidence]
- Ruled out: [rejected hypothesis 1], [rejected hypothesis 2]
- Reproduced with: [command or test]

Next steps:
- Verify hypothesis by [specific action]
- Apply fix in [file]
- Run [specific test] to confirm

Key context:
- The bug manifests as [symptom]
- Related service(s): [juniper-data/juniper-cascor/juniper-canopy]
- Profile(s) affected: [full/demo/dev]
```

### Template: Docker Compose / Service Orchestration Work

```bash
Continue [ORCHESTRATION TASK] in juniper-deploy.

Completed:
- Modified docker-compose.yml: [description]
- Updated .env.example or .env.demo if needed
- Updated scripts/ if needed

Remaining:
- Implement [specific service or profile change]
- Add/update integration tests in tests/
- Verify all profiles: docker compose --profile full config

Key context:
- Profiles: full (all real services), demo (auto-configured CasCor), dev (canopy demo mode)
- Service ports: juniper-data:8100, juniper-cascor:8200, juniper-canopy:8050
- Health endpoints: /v1/health on all services
- Validate: docker compose --profile full config
- Run tests: pip install -r requirements-test.txt && pytest tests/ -v
```

---

## Best Practices

1. **Handoff early, not late** — A handoff at 70% context usage is better than compaction at 95%
2. **One handoff per phase boundary** — Don't chain 5 handoffs for one task; batch related work
3. **Include the verification command** — Always tell the new thread how to check its work (`docker compose config`, `pytest tests/ -v`, etc.)
4. **Reference CLAUDE.md** — The new thread will read it automatically, but call out any project-specific conventions relevant to the remaining work
5. **Don't duplicate CLAUDE.md content** — The new thread already has it; only include task-specific context
6. **State the git status** — If files are staged, modified, or if a branch is in use, mention it

---

## Integration with Project Workflow

This procedure complements the existing development workflow in CLAUDE.md. When a thread handoff occurs during feature development:

- The new thread should verify it can validate Docker Compose configuration before making changes
- The new thread should re-read any file it plans to edit (fresh context, no assumptions)
- Note any cross-service dependencies or environment variable changes that affect multiple services
