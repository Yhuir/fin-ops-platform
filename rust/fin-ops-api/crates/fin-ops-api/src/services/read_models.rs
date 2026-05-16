use serde::{Deserialize, Serialize};
use serde_json::{json, Map, Value};
use uuid::Uuid;

use crate::repositories::read_models::{
    ReadModelRepository, ReadModelRepositoryError, SearchIndexRow, WorkbenchRowDetailRow,
    WorkbenchSnapshotRow,
};

const DEFAULT_SEARCH_LIMIT: i64 = 20;
const MAX_SEARCH_LIMIT: i64 = 100;

#[derive(Debug, thiserror::Error)]
pub enum ReadModelServiceError {
    #[error("read model not found")]
    NotFound { resource: &'static str },
    #[error("invalid request: {message}")]
    InvalidRequest {
        code: &'static str,
        message: &'static str,
    },
    #[error(transparent)]
    Repository(#[from] ReadModelRepositoryError),
}

pub struct ReadModelService<R> {
    repository: R,
}

impl<R> ReadModelService<R>
where
    R: ReadModelRepository,
{
    pub fn new(repository: R) -> Self {
        Self { repository }
    }

    pub async fn get_workbench(
        &self,
        query: WorkbenchMonthQuery,
    ) -> Result<Value, ReadModelServiceError> {
        let month = validate_month(query.month.as_deref())?;
        let snapshot = self
            .repository
            .find_workbench_snapshot(&month)
            .await?
            .ok_or(ReadModelServiceError::NotFound {
                resource: "workbench_read_model",
            })?;

        let read_model_status = ReadModelStatusDto::from_snapshot(&snapshot);
        let mut payload = object_payload(snapshot.payload, "workbench snapshot payload")?;
        payload
            .entry("month".to_owned())
            .or_insert_with(|| Value::String(month.clone()));
        payload.insert(
            "read_model_status".to_owned(),
            serde_json::to_value(read_model_status).unwrap_or(Value::Null),
        );

        Ok(sanitize_json(Value::Object(payload)))
    }

    pub async fn get_ignored_rows(
        &self,
        query: WorkbenchMonthQuery,
    ) -> Result<IgnoredWorkbenchRowsResponse, ReadModelServiceError> {
        let month = validate_month(query.month.as_deref())?;
        let snapshot = self
            .repository
            .find_workbench_snapshot(&month)
            .await?
            .ok_or(ReadModelServiceError::NotFound {
                resource: "workbench_read_model",
            })?;

        let read_model_status = ReadModelStatusDto::from_snapshot(&snapshot);
        let rows = match snapshot.ignored_rows {
            Value::Array(rows) => rows.into_iter().map(sanitize_json).collect(),
            _ => {
                return Err(invalid_request(
                    "invalid_read_model_payload",
                    "workbench ignored_rows must be an array",
                ))
            }
        };

        Ok(IgnoredWorkbenchRowsResponse {
            month,
            rows,
            read_model_status,
        })
    }

    pub async fn get_workbench_status(
        &self,
        query: WorkbenchMonthQuery,
    ) -> Result<WorkbenchReadModelStatusResponse, ReadModelServiceError> {
        let month = validate_month(query.month.as_deref())?;
        let snapshot = self
            .repository
            .find_workbench_snapshot(&month)
            .await?
            .ok_or(ReadModelServiceError::NotFound {
                resource: "workbench_read_model",
            })?;

        Ok(WorkbenchReadModelStatusResponse {
            month,
            read_model_status: ReadModelStatusDto::from_snapshot(&snapshot),
        })
    }

    pub async fn get_row_detail(
        &self,
        row_id: Uuid,
        query: WorkbenchRowDetailQuery,
    ) -> Result<WorkbenchRowDetailResponse, ReadModelServiceError> {
        let month = match query.month.as_deref() {
            Some(month) => Some(validate_month(Some(month))?),
            None => None,
        };
        let row = self
            .repository
            .find_workbench_row(row_id, month.as_deref())
            .await?
            .ok_or(ReadModelServiceError::NotFound {
                resource: "workbench_row",
            })?;

        Ok(WorkbenchRowDetailResponse {
            row: row_payload(row)?,
        })
    }

    pub async fn search(
        &self,
        query: SearchQuery,
    ) -> Result<SearchResponse, ReadModelServiceError> {
        let q = query.q.unwrap_or_default().trim().to_owned();
        let scope = normalize_scope(query.scope.as_deref());
        let month = normalize_search_month(query.month.as_deref())?;
        let status = normalize_status(query.status.as_deref())?;
        let project_name = clean_optional(query.project_name);
        let limit = query
            .limit
            .unwrap_or(DEFAULT_SEARCH_LIMIT)
            .clamp(1, MAX_SEARCH_LIMIT);

        if q.is_empty() {
            return Ok(SearchResponse::empty(
                q,
                scope,
                month,
                project_name,
                status,
                limit,
            ));
        }

        let entity_types = entity_types_for_scope(&scope);
        let month_filter = if month == "all" {
            None
        } else {
            Some(month.as_str())
        };
        let rows = self
            .repository
            .search_index_rows(
                &q,
                &entity_types,
                month_filter,
                project_name.as_deref(),
                status.as_deref(),
                limit,
            )
            .await?;

        Ok(SearchResponse::from_rows(
            q,
            scope,
            month,
            project_name,
            status,
            limit,
            rows,
        ))
    }
}

#[derive(Debug, Deserialize)]
pub struct WorkbenchMonthQuery {
    pub month: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct WorkbenchRowDetailQuery {
    pub month: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct SearchQuery {
    pub q: Option<String>,
    pub scope: Option<String>,
    pub month: Option<String>,
    pub project_name: Option<String>,
    pub status: Option<String>,
    pub limit: Option<i64>,
}

#[derive(Debug, Serialize)]
pub struct IgnoredWorkbenchRowsResponse {
    pub month: String,
    pub rows: Vec<Value>,
    pub read_model_status: ReadModelStatusDto,
}

#[derive(Debug, Serialize)]
pub struct WorkbenchReadModelStatusResponse {
    pub month: String,
    pub read_model_status: ReadModelStatusDto,
}

#[derive(Debug, Serialize)]
pub struct WorkbenchRowDetailResponse {
    pub row: Value,
}

#[derive(Clone, Debug, Serialize)]
pub struct ReadModelStatusDto {
    pub scope_key: String,
    pub scope_type: String,
    pub scope_month: Option<String>,
    pub schema_version: String,
    pub stale: bool,
    pub stale_reason: Option<String>,
    pub source_versions: Value,
    pub generated_at: String,
    pub rebuilt_at: String,
    pub updated_at: String,
    pub stale_seconds: i64,
    pub rebuild_task_id: Option<String>,
    pub api_strategy: &'static str,
}

impl ReadModelStatusDto {
    fn from_snapshot(row: &WorkbenchSnapshotRow) -> Self {
        Self {
            scope_key: row.scope_key.clone(),
            scope_type: row.scope_type.clone(),
            scope_month: row.scope_month.clone(),
            schema_version: row.schema_version.clone(),
            stale: row.stale,
            stale_reason: row.stale_reason.clone(),
            source_versions: sanitize_json(row.source_versions.clone()),
            generated_at: row.generated_at.clone(),
            rebuilt_at: row.generated_at.clone(),
            updated_at: row.updated_at.clone(),
            stale_seconds: row.stale_seconds,
            rebuild_task_id: row.rebuild_task_id.clone(),
            api_strategy: if row.stale {
                "return_stale_snapshot_with_status"
            } else {
                "return_ready_snapshot"
            },
        }
    }
}

#[derive(Debug, Serialize)]
pub struct SearchResponse {
    pub query: String,
    pub filters: SearchFiltersDto,
    pub summary: SearchSummaryDto,
    pub oa_results: Vec<SearchResultDto>,
    pub bank_results: Vec<SearchResultDto>,
    pub invoice_results: Vec<SearchResultDto>,
    pub read_model_status: SearchReadModelStatusDto,
}

impl SearchResponse {
    fn empty(
        query: String,
        scope: String,
        month: String,
        project_name: Option<String>,
        status: Option<String>,
        limit: i64,
    ) -> Self {
        Self {
            query,
            filters: SearchFiltersDto {
                scope,
                month,
                project_name,
                status,
                limit,
            },
            summary: SearchSummaryDto::default(),
            oa_results: Vec::new(),
            bank_results: Vec::new(),
            invoice_results: Vec::new(),
            read_model_status: SearchReadModelStatusDto {
                stale_result_count: 0,
                max_stale_seconds: 0,
                api_strategy: "empty_query",
            },
        }
    }

    fn from_rows(
        query: String,
        scope: String,
        month: String,
        project_name: Option<String>,
        status: Option<String>,
        limit: i64,
        rows: Vec<SearchIndexRow>,
    ) -> Self {
        let mut oa_results = Vec::new();
        let mut bank_results = Vec::new();
        let mut invoice_results = Vec::new();
        let mut stale_result_count = 0;
        let mut max_stale_seconds = 0;

        for row in rows {
            if row.stale {
                stale_result_count += 1;
                max_stale_seconds = max_stale_seconds.max(row.stale_seconds);
            }
            let result = SearchResultDto::from_row(row);
            match result.record_type.as_str() {
                "oa" => oa_results.push(result),
                "bank" => bank_results.push(result),
                "invoice" => invoice_results.push(result),
                _ => {}
            }
        }

        Self {
            query,
            filters: SearchFiltersDto {
                scope,
                month,
                project_name,
                status,
                limit,
            },
            summary: SearchSummaryDto {
                total: oa_results.len() + bank_results.len() + invoice_results.len(),
                oa: oa_results.len(),
                bank: bank_results.len(),
                invoice: invoice_results.len(),
            },
            oa_results,
            bank_results,
            invoice_results,
            read_model_status: SearchReadModelStatusDto {
                stale_result_count,
                max_stale_seconds,
                api_strategy: "search_index_rows_only",
            },
        }
    }
}

#[derive(Debug, Serialize)]
pub struct SearchFiltersDto {
    pub scope: String,
    pub month: String,
    pub project_name: Option<String>,
    pub status: Option<String>,
    pub limit: i64,
}

#[derive(Debug, Default, Serialize)]
pub struct SearchSummaryDto {
    pub total: usize,
    pub oa: usize,
    pub bank: usize,
    pub invoice: usize,
}

#[derive(Debug, Serialize)]
pub struct SearchReadModelStatusDto {
    pub stale_result_count: usize,
    pub max_stale_seconds: i64,
    pub api_strategy: &'static str,
}

#[derive(Debug, Serialize)]
pub struct SearchResultDto {
    pub row_id: String,
    pub record_type: String,
    pub month: String,
    pub zone_hint: String,
    pub matched_field: String,
    pub title: String,
    pub primary_meta: String,
    pub secondary_meta: String,
    pub status_label: String,
    pub jump_target: Value,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub group_id: Option<String>,
    pub entity_type: String,
    pub entity_id: String,
    pub source_kind: String,
    pub stale: bool,
    pub stale_seconds: i64,
    pub stale_reason: Option<String>,
    pub generated_at: String,
    pub rebuilt_at: String,
    pub updated_at: String,
}

impl SearchResultDto {
    fn from_row(row: SearchIndexRow) -> Self {
        let record_type = record_type_for_entity(&row.entity_type);
        let month = month_from_scope_month(&row.scope_month);
        let zone_hint = row.zone_hint.clone().unwrap_or_else(|| "open".to_owned());
        let group_id = string_from_json(&row.jump_target, "group_id")
            .or_else(|| string_from_json(&row.payload, "group_id"));
        let row_id =
            string_from_json(&row.jump_target, "row_id").unwrap_or_else(|| row.entity_id.clone());
        let primary_meta = primary_meta(&row);
        let secondary_meta = secondary_meta(&row);

        Self {
            row_id,
            record_type,
            month,
            zone_hint: zone_hint.clone(),
            matched_field: "searchable_text".to_owned(),
            title: row.title,
            primary_meta,
            secondary_meta,
            status_label: status_label(&zone_hint).to_owned(),
            jump_target: sanitize_json(row.jump_target),
            group_id,
            entity_type: row.entity_type,
            entity_id: row.entity_id,
            source_kind: row.source_kind,
            stale: row.stale,
            stale_seconds: row.stale_seconds,
            stale_reason: row.stale_reason,
            rebuilt_at: row.generated_at.clone(),
            generated_at: row.generated_at,
            updated_at: row.updated_at,
        }
    }
}

fn object_payload(
    value: Value,
    label: &'static str,
) -> Result<Map<String, Value>, ReadModelServiceError> {
    match value {
        Value::Object(map) => Ok(map),
        _ => Err(invalid_request("invalid_read_model_payload", label)),
    }
}

fn row_payload(row: WorkbenchRowDetailRow) -> Result<Value, ReadModelServiceError> {
    let mut payload = object_payload(row.payload, "workbench row payload")?;
    payload
        .entry("id".to_owned())
        .or_insert_with(|| Value::String(row.row_id.clone()));
    payload
        .entry("type".to_owned())
        .or_insert_with(|| Value::String(row.row_type.clone()));
    payload
        .entry("group_id".to_owned())
        .or_insert_with(|| row.group_key.map(Value::String).unwrap_or(Value::Null));
    payload.insert(
        "read_model_status".to_owned(),
        json!({
            "id": row.id,
            "scope_month": row.scope_month,
            "row_id": row.row_id,
            "row_type": row.row_type,
            "zone_hint": row.zone_hint,
            "stale": row.stale,
            "stale_seconds": row.stale_seconds,
            "stale_reason": row.stale_reason,
            "source_versions": sanitize_json(row.source_versions),
            "generated_at": row.generated_at,
            "rebuilt_at": row.generated_at,
            "updated_at": row.updated_at,
            "api_strategy": if row.stale { "return_stale_row_with_status" } else { "return_ready_row" }
        }),
    );

    Ok(sanitize_json(Value::Object(payload)))
}

fn validate_month(month: Option<&str>) -> Result<String, ReadModelServiceError> {
    let month = month
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .ok_or_else(|| {
            invalid_request("invalid_month", "month is required and must use YYYY-MM")
        })?;
    if month == "all" {
        return Err(invalid_request(
            "all_time_workbench_not_supported",
            "single-month workbench read model API does not serve month=all",
        ));
    }
    if is_yyyy_mm(month) {
        Ok(month.to_owned())
    } else {
        Err(invalid_request("invalid_month", "month must use YYYY-MM"))
    }
}

fn normalize_search_month(month: Option<&str>) -> Result<String, ReadModelServiceError> {
    let Some(month) = month.map(str::trim).filter(|value| !value.is_empty()) else {
        return Ok("all".to_owned());
    };
    if month == "all" {
        return Ok("all".to_owned());
    }
    if is_yyyy_mm(month) {
        Ok(month.to_owned())
    } else {
        Err(invalid_request(
            "invalid_month",
            "month must be all or use YYYY-MM",
        ))
    }
}

fn is_yyyy_mm(value: &str) -> bool {
    let bytes = value.as_bytes();
    bytes.len() == 7
        && bytes[0..4].iter().all(|byte| byte.is_ascii_digit())
        && bytes[4] == b'-'
        && bytes[5..7].iter().all(|byte| byte.is_ascii_digit())
        && matches!(
            &value[5..7],
            "01" | "02" | "03" | "04" | "05" | "06" | "07" | "08" | "09" | "10" | "11" | "12"
        )
}

fn clean_optional(value: Option<String>) -> Option<String> {
    value
        .map(|value| value.trim().to_owned())
        .filter(|value| !value.is_empty())
}

fn normalize_scope(scope: Option<&str>) -> String {
    match scope.map(str::trim).filter(|value| !value.is_empty()) {
        Some("oa") => "oa".to_owned(),
        Some("bank") => "bank".to_owned(),
        Some("invoice") => "invoice".to_owned(),
        _ => "all".to_owned(),
    }
}

fn normalize_status(status: Option<&str>) -> Result<Option<String>, ReadModelServiceError> {
    let Some(status) = status.map(str::trim).filter(|value| !value.is_empty()) else {
        return Ok(None);
    };
    let allowed = ["paired", "open", "ignored", "processed_exception"];
    if allowed.contains(&status) {
        Ok(Some(status.to_owned()))
    } else {
        Err(invalid_request(
            "invalid_status",
            "status must be paired, open, ignored, or processed_exception",
        ))
    }
}

fn entity_types_for_scope(scope: &str) -> Vec<String> {
    match scope {
        "oa" => vec!["oa_application".to_owned(), "oa_attachment".to_owned()],
        "bank" => vec!["bank_transaction".to_owned()],
        "invoice" => vec!["invoice".to_owned()],
        _ => vec![
            "oa_application".to_owned(),
            "oa_attachment".to_owned(),
            "bank_transaction".to_owned(),
            "invoice".to_owned(),
            "reconciliation_case".to_owned(),
            "project".to_owned(),
        ],
    }
}

fn record_type_for_entity(entity_type: &str) -> String {
    match entity_type {
        "bank_transaction" => "bank".to_owned(),
        "invoice" => "invoice".to_owned(),
        _ => "oa".to_owned(),
    }
}

fn month_from_scope_month(scope_month: &str) -> String {
    scope_month.get(0..7).unwrap_or(scope_month).to_owned()
}

fn status_label(zone_hint: &str) -> &'static str {
    match zone_hint {
        "paired" => "已配对",
        "ignored" => "已忽略",
        "processed_exception" => "已处理异常",
        _ => "未配对",
    }
}

fn primary_meta(row: &SearchIndexRow) -> String {
    join_meta([
        row.subtitle.as_deref(),
        row.amount.as_deref(),
        row.status.as_deref(),
    ])
}

fn secondary_meta(row: &SearchIndexRow) -> String {
    let month = month_from_scope_month(&row.scope_month);
    join_meta([
        row.project_name.as_deref(),
        row.project_id.as_deref(),
        Some(month.as_str()),
    ])
}

fn join_meta<const N: usize>(parts: [Option<&str>; N]) -> String {
    let values = parts
        .into_iter()
        .flatten()
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .collect::<Vec<_>>();
    if values.is_empty() {
        "—".to_owned()
    } else {
        values.join(" / ")
    }
}

fn string_from_json(value: &Value, key: &str) -> Option<String> {
    value
        .get(key)
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(ToOwned::to_owned)
}

fn sanitize_json(value: Value) -> Value {
    match value {
        Value::Object(map) => Value::Object(
            map.into_iter()
                .filter_map(|(key, value)| {
                    if is_sensitive_key(&key) {
                        None
                    } else {
                        Some((key, sanitize_json(value)))
                    }
                })
                .collect(),
        ),
        Value::Array(values) => Value::Array(values.into_iter().map(sanitize_json).collect()),
        other => other,
    }
}

fn is_sensitive_key(key: &str) -> bool {
    let lowered = key.to_ascii_lowercase();
    [
        "password",
        "token",
        "secret",
        "credential",
        "raw_file",
        "raw_content",
        "stack",
        "traceback",
    ]
    .iter()
    .any(|part| lowered.contains(part))
}

fn invalid_request(code: &'static str, message: &'static str) -> ReadModelServiceError {
    ReadModelServiceError::InvalidRequest { code, message }
}

#[cfg(test)]
mod tests {
    use async_trait::async_trait;

    use super::*;

    struct FixtureRepository {
        snapshot: Option<WorkbenchSnapshotRow>,
        row: Option<WorkbenchRowDetailRow>,
        search_rows: Vec<SearchIndexRow>,
    }

    #[async_trait]
    impl ReadModelRepository for FixtureRepository {
        async fn find_workbench_snapshot(
            &self,
            _month: &str,
        ) -> Result<Option<WorkbenchSnapshotRow>, ReadModelRepositoryError> {
            Ok(self.snapshot.clone())
        }

        async fn find_workbench_row(
            &self,
            _row_id: Uuid,
            _month: Option<&str>,
        ) -> Result<Option<WorkbenchRowDetailRow>, ReadModelRepositoryError> {
            Ok(self.row.clone())
        }

        async fn search_index_rows(
            &self,
            _query: &str,
            _entity_types: &[String],
            _month: Option<&str>,
            _project_name: Option<&str>,
            _zone_hint: Option<&str>,
            _limit: i64,
        ) -> Result<Vec<SearchIndexRow>, ReadModelRepositoryError> {
            Ok(self.search_rows.clone())
        }
    }

    #[tokio::test]
    async fn workbench_returns_snapshot_payload_with_stale_status() {
        let service = ReadModelService::new(FixtureRepository {
            snapshot: Some(snapshot_fixture(true)),
            row: None,
            search_rows: Vec::new(),
        });

        let response = service
            .get_workbench(WorkbenchMonthQuery {
                month: Some("2026-05".to_owned()),
            })
            .await
            .unwrap();

        assert_eq!(response["month"], "2026-05");
        assert_eq!(response["read_model_status"]["stale"], true);
        assert_eq!(response["read_model_status"]["stale_seconds"], 420);
        assert_eq!(
            response["read_model_status"]["rebuilt_at"],
            response["read_model_status"]["generated_at"]
        );
        assert_eq!(
            response["read_model_status"]["api_strategy"],
            "return_stale_snapshot_with_status"
        );
    }

    #[tokio::test]
    async fn workbench_rejects_all_time_request_path() {
        let service = ReadModelService::new(empty_repository());

        let error = service
            .get_workbench(WorkbenchMonthQuery {
                month: Some("all".to_owned()),
            })
            .await
            .unwrap_err();

        assert!(matches!(
            error,
            ReadModelServiceError::InvalidRequest {
                code: "all_time_workbench_not_supported",
                ..
            }
        ));
    }

    #[tokio::test]
    async fn row_detail_sanitizes_sensitive_payload_keys() {
        let row_id = Uuid::parse_str("0196f550-cc6e-7000-8000-000000000111").unwrap();
        let service = ReadModelService::new(FixtureRepository {
            snapshot: None,
            row: Some(WorkbenchRowDetailRow {
                id: "0196f550-cc6e-7000-8000-000000000999".to_owned(),
                scope_month: "2026-05-01".to_owned(),
                row_id: row_id.to_string(),
                row_type: "bank".to_owned(),
                zone_hint: "open".to_owned(),
                group_key: None,
                payload: json!({
                    "id": row_id.to_string(),
                    "type": "bank",
                    "counterparty_name": "供应商",
                    "raw_content": "must not leak"
                }),
                source_versions: json!({"fact_updated_at": "2026-05-16T00:00:00Z"}),
                generated_at: "2026-05-16T00:00:00Z".to_owned(),
                stale: false,
                stale_seconds: 0,
                stale_reason: None,
                updated_at: "2026-05-16T00:00:00Z".to_owned(),
            }),
            search_rows: Vec::new(),
        });

        let response = service
            .get_row_detail(
                row_id,
                WorkbenchRowDetailQuery {
                    month: Some("2026-05".to_owned()),
                },
            )
            .await
            .unwrap();

        assert!(response.row.get("raw_content").is_none());
        assert_eq!(response.row["type"], "bank");
    }

    #[tokio::test]
    async fn search_groups_results_by_frontend_record_type() {
        let service = ReadModelService::new(FixtureRepository {
            snapshot: None,
            row: None,
            search_rows: vec![
                search_row("bank_transaction", "open"),
                search_row("invoice", "paired"),
                search_row("oa_application", "ignored"),
            ],
        });

        let response = service
            .search(SearchQuery {
                q: Some("供应商".to_owned()),
                scope: Some("all".to_owned()),
                month: Some("2026-05".to_owned()),
                project_name: None,
                status: None,
                limit: Some(20),
            })
            .await
            .unwrap();

        assert_eq!(response.summary.total, 3);
        assert_eq!(response.bank_results[0].record_type, "bank");
        assert_eq!(response.invoice_results[0].record_type, "invoice");
        assert_eq!(response.oa_results[0].record_type, "oa");
    }

    fn empty_repository() -> FixtureRepository {
        FixtureRepository {
            snapshot: None,
            row: None,
            search_rows: Vec::new(),
        }
    }

    fn snapshot_fixture(stale: bool) -> WorkbenchSnapshotRow {
        WorkbenchSnapshotRow {
            scope_key: "workbench:2026-05".to_owned(),
            scope_type: "month".to_owned(),
            scope_month: Some("2026-05-01".to_owned()),
            schema_version: "2026-05-workbench-v1".to_owned(),
            payload: json!({
                "month": "2026-05",
                "oa_status": {"code": "ready", "message": "OA 已同步"},
                "summary": {
                    "oa_count": 0,
                    "bank_count": 1,
                    "invoice_count": 0,
                    "paired_count": 0,
                    "open_count": 1,
                    "exception_count": 0
                },
                "paired": {"groups": []},
                "open": {"groups": []}
            }),
            ignored_rows: json!([]),
            summary: json!({"open_count": 1}),
            source_versions: json!({"fact_updated_at": "2026-05-16T00:00:00Z"}),
            generated_at: "2026-05-16T00:00:00Z".to_owned(),
            stale,
            stale_seconds: stale.then_some(420).unwrap_or(0),
            stale_reason: stale.then(|| "import.batch_confirmed".to_owned()),
            rebuild_task_id: stale.then(|| "0196f550-cc6e-7000-8000-000000000222".to_owned()),
            updated_at: "2026-05-16T00:00:00Z".to_owned(),
        }
    }

    fn search_row(entity_type: &str, zone_hint: &str) -> SearchIndexRow {
        SearchIndexRow {
            id: Uuid::new_v4().to_string(),
            entity_type: entity_type.to_owned(),
            entity_id: Uuid::new_v4().to_string(),
            source_kind: format!("app.{entity_type}"),
            scope_month: "2026-05-01".to_owned(),
            title: "供应商".to_owned(),
            subtitle: Some("测试项目".to_owned()),
            amount: Some("100.00".to_owned()),
            status: Some("open".to_owned()),
            zone_hint: Some(zone_hint.to_owned()),
            project_id: Some("P001".to_owned()),
            project_name: Some("测试项目".to_owned()),
            jump_target: json!({
                "month": "2026-05",
                "row_id": "0196f550-cc6e-7000-8000-000000000111",
                "zone_hint": zone_hint
            }),
            payload: json!({}),
            source_versions: json!({}),
            generated_at: "2026-05-16T00:00:00Z".to_owned(),
            stale: false,
            stale_seconds: 0,
            stale_reason: None,
            updated_at: "2026-05-16T00:00:00Z".to_owned(),
        }
    }
}
