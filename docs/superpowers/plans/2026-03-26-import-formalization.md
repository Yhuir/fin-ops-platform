# Import Formalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a production-style import flow that accepts multiple real invoice/bank files, auto-detects templates, previews normalized rows, and lets the React app confirm selected files into the existing import pipeline.

**Architecture:** Add a backend file-import adaptation layer ahead of `ImportNormalizationService`, with template detection, parser modules, session persistence, and file-based preview/confirm APIs. Add a dedicated React Import Center route that uploads files, displays per-file preview stats and row details, and confirms selected files through the new APIs.

**Tech Stack:** Python stdlib + `openpyxl` + `xlrd`, existing in-memory backend services, React 18, TypeScript, Vite, Vitest, Testing Library.

## Formalization Follow-up

在首版计划落地后，再补一轮正式化收口：

- [ ] 为导入会话、批次、发票、流水、匹配运行增加本地持久化
- [ ] 为发票导入增加自动区分进项 / 销项，并允许前端手动改判后重试
- [ ] 为导入中心增加模板库、重试、批次下载、批次撤销
- [ ] 确认导入后自动触发匹配引擎，并让 `/api/workbench` 回读实时导入数据

---

### Task 1: Add backend red tests for file-based preview and template detection

**Files:**
- Create: `tests/test_import_file_service.py`
- Modify: `tests/test_import_api.py`
- Reference: `backend/src/fin_ops_platform/services/imports.py`

- [ ] **Step 1: Write the failing service tests**

Add tests that use the real sample files under:

- `发票信息导出1-3月/`
- `测试用银行流水下载/`

Cover:

- invoice `.xlsx` recognized as `invoice_export`
- ICBC `.xlsx` recognized as `icbc_historydetail`
- PingAn `.xlsx` recognized as `pingan_transaction_detail`
- CMBC `.xlsx` recognized as `cmbc_transaction_detail`
- CCB `.xls` recognized as `ccb_transaction_detail`
- CEB `.xls` recognized as `ceb_transaction_detail`
- mixed multi-file preview isolates a bad file

- [ ] **Step 2: Run the failing tests**

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_import_file_service tests.test_import_api -v
```

Expected:

- FAIL because file import services and endpoints do not exist yet

- [ ] **Step 3: Write minimal backend scaffolding**

Create lightweight placeholder types / methods so tests fail on behavior instead of missing imports:

- file preview session model
- file import service shell
- route handlers shell

- [ ] **Step 4: Re-run the same tests**

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_import_file_service tests.test_import_api -v
```

Expected:

- FAIL on unimplemented detection / parsing behavior

### Task 2: Implement workbook readers, template detector, and per-template parsers

**Files:**
- Create: `backend/src/fin_ops_platform/services/import_file_types.py`
- Create: `backend/src/fin_ops_platform/services/import_file_readers.py`
- Create: `backend/src/fin_ops_platform/services/import_template_detector.py`
- Create: `backend/src/fin_ops_platform/services/import_template_parsers.py`
- Modify: `backend/src/fin_ops_platform/services/imports.py`
- Test: `tests/test_import_file_service.py`

- [ ] **Step 1: Write the next failing parser-focused tests**

Add assertions for:

- detected template code
- extracted header row index
- parsed row count > 0
- mapped normalized fields contain required keys for one sample per template

- [ ] **Step 2: Run the parser-focused tests**

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_import_file_service.ImportFileServiceTests -v
```

Expected:

- FAIL on detection / parser assertions

- [ ] **Step 3: Implement readers and parsers**

Implement:

- `.xlsx` reader with `openpyxl`
- `.xls` reader with `xlrd`
- detector rules for six templates
- parser modules that map raw rows into the existing normalization input shape

- [ ] **Step 4: Re-run the parser-focused tests**

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_import_file_service.ImportFileServiceTests -v
```

Expected:

- PASS

### Task 3: Implement file preview sessions and backend APIs

**Files:**
- Modify: `backend/src/fin_ops_platform/services/imports.py`
- Modify: `backend/src/fin_ops_platform/app/server.py`
- Modify: `README.md`
- Test: `tests/test_import_api.py`

- [ ] **Step 1: Write failing API tests for file preview / session / confirm**

Add tests for:

- `POST /imports/files/preview`
- `GET /imports/files/sessions/{session_id}`
- `POST /imports/files/confirm`
- selected files only are confirmed

- [ ] **Step 2: Run the API tests**

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_import_api.ImportApiTests -v
```

Expected:

- FAIL because endpoints are missing or response shape is wrong

- [ ] **Step 3: Implement file import session storage and endpoints**

Implement:

- session state in memory
- per-file preview aggregation
- selected-file confirm behavior
- unified JSON response shape

- [ ] **Step 4: Re-run the API tests**

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_import_api.ImportApiTests -v
```

Expected:

- PASS

### Task 4: Add frontend red tests for the Import Center

**Files:**
- Create: `web/src/test/ImportCenterPage.test.tsx`
- Create: `web/src/test/importApiMock.ts`
- Modify: `web/src/test/App.test.tsx`
- Reference: `web/src/app/router.tsx`

- [ ] **Step 1: Write failing frontend tests**

Cover:

- navigation to `/imports`
- multi-file upload preview request
- per-file preview card rendering
- row detail expansion
- confirm selected files request
- file-level error rendering

- [ ] **Step 2: Run the failing frontend tests**

Run:

```bash
cd web
npm run test -- --run
```

Expected:

- FAIL because the page / route / API layer do not exist

- [ ] **Step 3: Add minimal route and page shell**

Create a minimal `ImportCenterPage` and route so tests fail on behavior instead of missing modules.

- [ ] **Step 4: Re-run frontend tests**

Run:

```bash
cd web
npm run test -- --run
```

Expected:

- FAIL on upload / preview / confirm behavior

### Task 5: Implement the React Import Center

**Files:**
- Create: `web/src/pages/ImportCenterPage.tsx`
- Create: `web/src/features/imports/api.ts`
- Create: `web/src/features/imports/types.ts`
- Create: `web/src/components/imports/FileDropzone.tsx`
- Create: `web/src/components/imports/ImportPreviewCard.tsx`
- Create: `web/src/components/imports/ImportRowResultsTable.tsx`
- Modify: `web/src/app/router.tsx`
- Modify: `web/src/app/App.tsx`
- Modify: `web/src/app/styles.css`
- Test: `web/src/test/ImportCenterPage.test.tsx`

- [ ] **Step 1: Write the next failing UI-state tests**

Add assertions for:

- loading state during preview
- empty state before upload
- selected-file confirm state
- success summary after confirm

- [ ] **Step 2: Run the frontend tests**

Run:

```bash
cd web
npm run test -- --run
```

Expected:

- FAIL on missing interaction details

- [ ] **Step 3: Implement the Import Center UI**

Implement:

- top-nav entry
- drag-and-drop / file picker upload
- preview list
- row detail expansion
- checkbox-based file selection
- confirm action
- loading / empty / error / success states

- [ ] **Step 4: Re-run the frontend tests**

Run:

```bash
cd web
npm run test -- --run
```

Expected:

- PASS

### Task 6: Verify end-to-end and update docs

**Files:**
- Modify: `README.md`
- Modify: `web/README.md`
- Modify: `docs/dev/import-normalization-samples.md`
- Modify: `docs/dev/reconciliation-workbench-v2-frontend.md`
- Modify: `docs/dev/reconciliation-workbench-v2-testing.md`

- [ ] **Step 1: Run backend full test suite**

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest discover -s tests -v
```

Expected:

- PASS

- [ ] **Step 2: Run frontend test suite**

Run:

```bash
cd web
npm run test -- --run
```

Expected:

- PASS

- [ ] **Step 3: Run frontend production build**

Run:

```bash
cd web
npm run build
```

Expected:

- PASS

- [ ] **Step 4: Update docs to match implementation**

Document:

- supported file templates
- new APIs
- Import Center route
- dependency requirements
- manual acceptance flow
