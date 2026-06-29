# GSD Quick Plan: bank-flow-rule-batches boundary slice

Date: 2026-06-29

## Goal

Create a documentation and module-boundary slice for replacing `免OA流水批量处理` with `流水规则批量处理`, without implementing code.

## Scope

- Add a new module document set under `docs/modules/bank-flow-rule-batches/`.
- Register the new module in module inventory and module index.
- Update impacted boundary documents for canonical facts, read models, bank details, workbench relations, reconciliation workbench, and API contracts.
- Clarify legacy no-OA is superseded for new feature work and requires controlled rebaseline.

## Non-goals

- No frontend implementation.
- No backend implementation.
- No database migration.
- No Playwright test code yet.
- No production data rebaseline.

## Acceptance

- The module boundary explicitly defines owners, inputs, outputs, persistence/read model plan, dependencies, and deletion conditions.
- The API contract names planned endpoints and removes ambiguity around `selected_tag_codes`.
- The E2E spec describes the full browser business flow to implement next.
- Verification runs on docs.
