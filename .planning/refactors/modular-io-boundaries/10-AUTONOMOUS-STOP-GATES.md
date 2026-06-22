# Autonomous Stop Gates

**Purpose:** Define what stops an unattended run and what should be recorded as deferred while continuing.

## Principle

The autonomous loop should keep moving across independent modules. Missing staging DB, missing local `PGSQL_URL`, missing root SSH, and unavailable production DB evidence are not hard blockers.

Only stop when continuing would be unsafe, destructive, or meaningless.

## Hard Stop Gates

Stop immediately if any of these occur:

1. **Cannot enter a safe direct-Dev state in the main repository**
   - Main repository working tree is dirty at automation start.
   - Current branch would be `main`.
   - Git state is ambiguous enough that committing could include user changes.
   - Local `dev` cannot fast-forward from `origin/dev`.
   - Merging `origin/main` into `dev` conflicts.
   - Aligning `dev` would require rebase, reset or force-push.

2. **A secret is required**
   - The task cannot proceed without a password, token, cookie, production DSN, private key, or root secret.
   - Do not ask the user for the secret.
   - Record the needed secret type and stop.

3. **Production write would be required**
   - Any action would write production database, queue, readiness, files, systemd state, or OA state.
   - Stop unless the user has explicitly approved a runbook with backup, impact, rollback, and maintenance window.

4. **Destructive local operation would be required in the main repository**
   - No `git reset --hard`, `git checkout --`, mass delete, branch deletion, or history rewrite in the main repository working tree.

5. **Business semantics are ambiguous**
   - Required behavior cannot be determined from code/docs/tests.
   - A reasonable default would risk changing finance rules, permissions, amounts, state transitions, or audit meaning.

6. **No independent module remains**
   - All remaining modules require the same unresolved hard gate.

7. **Unsafe Go/Fiber migration would be required**
   - The module is not listed in `11-GO-HOT-PATH-CARVE-OUT.md`.
   - Go implementation would start before performance evidence, IO contract, shadow run or rollback gates pass.
   - Fiber would be used to run long background work inside a request handler.
   - Python and Go workers would both ack, publish or write readiness for the same authoritative event/scope.

## Soft Gates: Record And Continue

Do not stop for these. Record the condition and continue to the next independent module:

- No local `PGSQL_URL`.
- No staging database.
- `finops-prod-root` unavailable.
- No passwordless sudo.
- Production read-only evidence unavailable.
- A specific module's tests fail after repair attempts.
- A module grows beyond its planned boundary.
- `origin/dev` and `origin/main` are diverged but can be merged cleanly.
- A verification command is unavailable but a local/fake substitute exists.
- A Go candidate lacks enough performance evidence.
- A Go candidate lacks shadow-run or equivalence-test readiness.
- A Go candidate is not yet safe to implement but Python boundary hardening can continue.

Soft-gated modules should be marked:

```text
deferred-production-evidence
deferred-module-failure
deferred-scope-too-large
deferred-unrelated-dirty-context
go-candidate-deferred
```

## Failure Attempt Limit

For each module:

- Try at most 3 repair iterations for the same failing test/check.
- If issue count does not decrease, stop working that module.
- Preserve failure evidence.
- Continue to the next module.

## Production Evidence Policy

Without staging DB or local `PGSQL_URL`, production evidence is best effort.

Allowed:

- `ssh finops-prod` non-privileged read-only checks.
- Public health endpoint checks.
- File existence checks where permission allows.

Forbidden:

- Reading secrets.
- sudo prompts.
- production writes.
- queue mutation.
- readiness mutation.
- DB writes.

Missing production evidence must not block autonomous progress. It blocks only claims of full production closure.

## Completion Labels

Use these labels in `autonomous/STATE.md`:

| Label | Meaning |
| --- | --- |
| `closed-autonomous` | Local/fake/stub/tests/docs complete; no required production evidence. |
| `production-evidence-deferred` | Code/docs/tests complete; real production DB/worker proof unavailable and recorded. |
| `needs-human-production-gate` | Production write, root secret, or privileged action required. |
| `deferred-module-failure` | Module-specific failure preserved; run continued elsewhere. |
| `go-candidate-deferred` | Go/Fiber/Go Worker candidate failed admission gates; no Go implementation started. |
| `blocked-hard-stop` | Run stopped due to hard gate. |
