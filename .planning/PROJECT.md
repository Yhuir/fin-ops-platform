# fin-ops-platform

## What This Is

`fin-ops-platform` is an existing finance operations platform with a Python backend, React frontend, PostgreSQL-backed read models, runtime workers, and module-specific documentation. This planning workspace is initialized for page-by-page analysis and feature planning without rewriting the existing architecture.

## Core Value

Preserve production finance workflow correctness while improving individual pages through isolated, reviewable GSD phases.

## Requirements

### Validated

- The repository already contains module-level product, architecture, operation, and test documentation.
- `.planning/codebase/` is the global codebase map and should not be overwritten for per-page analysis.

### Active

- [ ] **PAGE-01**: External turnover ledger page analysis and improvement planning is saved in its own phase directory.
- [ ] **PAGE-02**: Bank details page analysis and improvement planning is saved in its own phase directory.
- [ ] **PAGE-03**: Tax offset page analysis and improvement planning is saved in its own phase directory.
- [ ] **PAGE-04**: The global `.planning/codebase/` map remains repository-wide and is not overwritten by page-specific analysis.
- [ ] **PAGE-05**: Every page phase records module docs, code entry points, risks, and verification strategy before implementation.
- [ ] **PAGE-06**: Reconciliation workbench page analysis and improvement planning is saved in its own phase directory.
- [ ] **PAGE-07**: Cost statistics page analysis and improvement planning is saved in its own phase directory.
- [ ] **PAGE-08**: Pending invoices page analysis and improvement planning is saved in its own phase directory.
- [ ] **PAGE-09**: Input invoice usage page analysis and improvement planning is saved in its own phase directory.
- [ ] **PAGE-10**: OA pending payments page analysis and improvement planning is saved in its own phase directory.
- [ ] **PAGE-11**: Output invoice collections page analysis and improvement planning is saved in its own phase directory.
- [ ] **PAGE-12**: No-OA bank batches page analysis and improvement planning is saved in its own phase directory.
- [ ] **PAGE-13**: Batch accounting page analysis and improvement planning is saved in its own phase directory.
- [ ] **PAGE-14**: ETC tickets page analysis and improvement planning is saved in its own phase directory.
- [ ] **PAGE-15**: Settings page analysis and improvement planning is saved in its own phase directory.
- [ ] **PAGE-16**: App Health operations page analysis and improvement planning is saved in its own phase directory.
- [ ] **PAGE-17**: Bank transaction import page analysis and improvement planning is saved in its own phase directory.
- [ ] **PAGE-18**: Invoice import page analysis and improvement planning is saved in its own phase directory.
- [ ] **PAGE-19**: ETC invoice import page analysis and improvement planning is saved in its own phase directory.

### Out of Scope

- Rebuilding the GSD global codebase map per page — per-page analysis belongs in phase artifacts.
- Rewriting core product architecture during phase creation — implementation changes require explicit phase plans and verification.
- Changing business behavior, APIs, UI, read models, workers, permissions, or deployment from this scaffolding step.

## Context

- Repository instructions require reading `AGENTS.md`, `README.md`, architecture docs, module docs, and existing tests before changes.
- Page/module facts belong under `docs/modules/<module>/` when they become long-term source of truth.
- GSD page analysis should first create `CONTEXT.md`, `RESEARCH.md`, and plan files inside each page-specific phase directory.
- Parallel Codex threads should work in separate worktrees and must not modify `.planning/codebase/*.md` for page-specific analysis.

## Constraints

- **Planning isolation**: `.planning/codebase/` remains a global map; each page writes only its own `.planning/phases/<phase>/` artifacts.
- **Repository boundaries**: Backend business logic stays in services/repositories/workers; `server.py` remains HTTP routing and dependency assembly.
- **Read model governance**: Read model refreshes must go through gateway/registry/queue boundaries and cannot fake freshness.
- **Docs governance**: Long-term page facts update `docs/modules/<module>/`; temporary analysis remains in phase artifacts.
- **Testing governance**: Behavior changes must evaluate the repository's seven test categories and use module test matrices.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Keep `.planning/codebase/` global-only | Re-running map-codebase per page overwrites the same seven documents and causes merge conflicts across threads. | ✓ Adopted |
| Store page analysis in separate phases | Phase directories preserve per-page context, research, plans, and verification without overwriting other pages. | ✓ Adopted |
| Use page-specific Codex worktree threads for parallel analysis | Worktrees isolate in-progress changes and reduce planning artifact conflicts. | ✓ Adopted |

---
*Last updated: 2026-06-16 after adding phase directories for all registered pages*
