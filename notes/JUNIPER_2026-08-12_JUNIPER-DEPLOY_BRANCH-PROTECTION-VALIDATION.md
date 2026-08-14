# Branch-Protection Validation — juniper-deploy

**Project**: Juniper
**Sub-Project**: juniper-deploy
**Author**: Paul Calnon
**License**: MIT License
**Version**: 1.0.0
**Last Updated**: 2026-08-12

---

Records the outcome of the 2026-08-12 fleet ruleset validation.

`main` is governed by an 8-rule ruleset uniform across all 9 publishing repos:
`code_quality`, `code_scanning`, `creation`, `deletion`, `non_fast_forward`,
`pull_request`, `required_signatures`, `required_status_checks`.

Only `required_status_checks` is per-repo — it names this repo's actual CI job
names. The canonical per-repo lists, the derivation method, and the Tier 2
hardening roadmap live in juniper-ml:

`notes/JUNIPER_2026-08-10_JUNIPER-ECOSYSTEM_REQUIRED-STATUS-CHECK-CONTEXT-LISTS.md`

**Operational notes**

- `strict_required_status_checks_policy` is **on** — a PR must be current with
  `main` to merge. Retained deliberately as the anti-storm guarantee.
- `require_last_push_approval` is **off**. With `required_approving_review_count: 0`
  it added no review workflow and made any owner-authored PR unmergeable except by
  admin bypass.
- An unsigned commit anywhere on a PR branch blocks the merge under
  `required_signatures`. Squash-merge does **not** rescue it. Commits made through
  the REST contents API are unsigned; the GraphQL `createCommitOnBranch` mutation
  produces a signed commit.
- If a PR sits at `CLEAN` without merging, **re-arm auto-merge** — a ruleset edit is
  not a PR event, so nothing re-evaluates the queue. Do not admin-merge.

## CI hardening + fleet parity (2026-08-13/14)

juniper-deploy carried the **thinnest CI in the fleet** — six jobs — while shipping ~30
Python files and ~45 markdown files. deploy#175 added three gates, all wired into the
existing `Quality Gate` and now also named explicitly in the ruleset:

| Context | Closes |
|---|---|
| `Analyze (python)` | no static analysis existed at all |
| `Documentation Links` | ~45 markdown files, zero link validation |
| `Security Scans` | no dependency CVE screen (audits `requirements-test.txt`) |

Two items from the original Tier 2 roadmap were verified **not applicable** here and
deliberately skipped: `Dependency Documentation` (no `conf/`, so the generator has nothing
to write) and `Lockfile Freshness` (no lockfile in the repo). That roadmap was derived from
check *names* across the fleet, and name-level inference over-reports — always confirm
against job contents.

**Ruleset now matches the fleet's 8 rules.** `code_scanning` had been removed because it
required **Trivy**, which never uploads on PR refs, making it permanently unsatisfiable. It
is restored scoped to **`CodeQL` only**, which deploy#175's `codeql.yml` does upload — on
both `refs/heads/main` and PR refs. Never list a tool that does not upload SARIF for this
repo: that is exactly how the 2026-08-10 fleet-union list (7 tools) blocked all nine repos.

`codeql.yml` is deliberately **not** path-filtered, because the `code_scanning` rule requires
analysis results *for the pull request* — a `paths:` filter would leave docs-only PRs with no
analysis and block them forever.

**Duplicate CI runs** eliminated (deploy#176): `on.push` is `[main, develop]` only. The
topic-branch globs (`feature/**`, `fix/**`, `chore/**`) plus `pull_request` meant both events
fired for the same commit and every job ran twice; the concurrency group is keyed on
`github.ref`, which differs between a branch push and a PR, so `cancel-in-progress` never
collapsed the pair.
