# Canonical Facts Wave 5: ETC Legacy SLO Probe Removal

日期：2026-06-28

## Scope

删除生产默认 HTTP SLO 对 legacy `/api/etc/batches*` 的依赖，避免默认运行证据继续把旧 ETC batches endpoint 当作 canonical facts 主链路。

## Evidence

- `http_slo_probe.DEFAULT_API_PROBES` 仍包含 `etc_business_batches`。
- `http_slo_probe.DEFAULT_API_PROBES` 不再包含 `etc_batches`。
- `tests/test_http_slo_probe.py::HttpSloProbeTests.test_default_probes_cover_page_domains_and_known_slow_endpoints` 明确禁止 `etc_batches` 和 `/api/etc/batches` 回到默认 probes。

## Changes

- `backend/src/fin_ops_platform/tools/http_slo_probe.py`
  - 删除默认 probe：`HttpProbe("etc_batches", "/api/etc/batches?page=1&page_size=50", ...)`。
- `tests/test_http_slo_probe.py`
  - 新增默认 probe 断言，禁止 legacy ETC batches endpoint 回到生产默认 SLO。
- `docs/modules/canonical-facts/implementation-notes.md`
- `docs/modules/canonical-facts/tests.md`
- `docs/modules/app-health-operations/tests.md`

## Verification

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_http_slo_probe.HttpSloProbeTests.test_default_probes_cover_page_domains_and_known_slow_endpoints -v
```

结果：通过。

## Closure Note

本 slice 删除的是生产默认观测链路中的旧 endpoint，不删除 legacy `/api/etc/batches*` 兼容 API 本体。该兼容 API 仍 production 可达，因此 ETC legacy batch source-of-truth deletion 仍未 closure。下一步必须删除或替换兼容 API 本身，或继续拆除其它 production 可达旧链路。
