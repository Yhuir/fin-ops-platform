---
quick_id: 260729-ohq
mode: quick-validate-inline
status: completed
completed_at: 2026-07-29
must_haves:
  truths:
    - Submitted ETC business batch etc_20260720_001 contains the four verified canonical ETC invoices and converges from 64 / 3686.36 to 68 / 3740.82.
    - OA draft data and the closed reconciliation task ETC-RECON-241132 remain byte-for-byte unchanged.
    - ETC submitted detail and Workbench both derive the repaired membership from the same canonical ETC facts and active relation chain.
  artifacts:
    - One owner-scoped, dry-run-first, idempotent repair path reuses existing ETC invoice/link persistence and Workbench refresh boundaries.
    - Focused tests protect amount, membership, duplicate, concurrent-change, missing-source and idempotent-repeat contracts.
    - Production before/after evidence, rollback payload, audit result and latency measurements are recorded.
  key_links:
    - Canonical invoice evidence is promoted through the existing ETC invoice normalization and batch link contracts.
    - The submitted business batch owns its actual member count and amount; no UI/read-model-only correction is allowed.
    - Workbench is refreshed through the durable matching/read-model boundary and is never edited directly.
---

# Repair submitted ETC batch etc_20260720_001

## Task 1: Fail-closed production preflight

- Read the submitted business batch, its 64 current members, the four target canonical invoices, specialized ETC facts, OA record and closed reconciliation task.
- Prove the four invoice numbers, dates, amounts and operator-approved batch ownership; reject duplicates, amount drift, wrong batch status or concurrent version drift. Record missing PDF/XML honestly and do not fabricate attachment facts.
- Capture exact before-state hashes and a reversible rollback payload before any write.

## Task 2: Minimal canonical repair path

- Reuse existing ETC normalization, strict batch invoice links and repository transaction boundaries.
- Add only the missing specialized ETC facts and membership required for the four verified invoices; update the batch summary from actual members in the same transaction.
- Hide/link the corresponding generic canonical rows through the existing ETC overlap contract, then enqueue the exact Workbench matching/refresh scopes.
- Do not modify OA draft fields, the closed reconciliation task, unrelated batches, Redis, API DTOs or UI code.
- Add one focused plan/tool test covering exact inputs, partial-state rejection, idempotence and official Workbench lifecycle refresh.

## Task 3: Release and production closure

- Run focused tests, lint, boundary/docs checks and inspect the final diff.
- Commit and push `main`, then deploy through `scripts/deploy-oa.sh`.
- Run the production command in dry-run mode, apply once, replay idempotently, wait for the durable Workbench chain and verify 68 / 3740.82 in both ETC and Workbench.
- Prove OA and reconciliation hashes are unchanged, System Audit passes, no stale queue state remains, and measure direct/API/page-chain latency.
- Remove any target-specific temporary repair input after verification; keep only a justified reusable owner-scoped repair capability.
