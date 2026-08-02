# Phase 13 Deferred Items

- 13-07 scope scan found four stale test-only references to the removed `AccessControlService.required_permission` field in `tests/test_etc_backend.py` and `tests/test_etc_invoice_pdf_bundle_service.py`. The 13-07 scope note explicitly limits edits to its listed files and assigns cross-page/full-repository cleanup to the later phase verification plan, so these callers were not changed here.
