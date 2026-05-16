use async_trait::async_trait;
use serde_json::Value;
use sqlx::{PgPool, Row};
use uuid::Uuid;

#[derive(Clone, Debug)]
pub struct WorkbenchSnapshotRow {
    pub scope_key: String,
    pub scope_type: String,
    pub scope_month: Option<String>,
    pub schema_version: String,
    pub payload: Value,
    pub ignored_rows: Value,
    pub summary: Value,
    pub source_versions: Value,
    pub generated_at: String,
    pub stale: bool,
    pub stale_seconds: i64,
    pub stale_reason: Option<String>,
    pub rebuild_task_id: Option<String>,
    pub updated_at: String,
}

#[derive(Clone, Debug)]
pub struct WorkbenchRowDetailRow {
    pub id: String,
    pub scope_month: String,
    pub row_id: String,
    pub row_type: String,
    pub zone_hint: String,
    pub group_key: Option<String>,
    pub payload: Value,
    pub source_versions: Value,
    pub generated_at: String,
    pub stale: bool,
    pub stale_seconds: i64,
    pub stale_reason: Option<String>,
    pub updated_at: String,
}

#[derive(Clone, Debug)]
pub struct SearchIndexRow {
    pub id: String,
    pub entity_type: String,
    pub entity_id: String,
    pub source_kind: String,
    pub scope_month: String,
    pub title: String,
    pub subtitle: Option<String>,
    pub amount: Option<String>,
    pub status: Option<String>,
    pub zone_hint: Option<String>,
    pub project_id: Option<String>,
    pub project_name: Option<String>,
    pub jump_target: Value,
    pub payload: Value,
    pub source_versions: Value,
    pub generated_at: String,
    pub stale: bool,
    pub stale_seconds: i64,
    pub stale_reason: Option<String>,
    pub updated_at: String,
}

#[derive(Debug, thiserror::Error)]
pub enum ReadModelRepositoryError {
    #[error(transparent)]
    Database(#[from] sqlx::Error),
}

#[async_trait]
pub trait ReadModelRepository: Send + Sync {
    async fn find_workbench_snapshot(
        &self,
        month: &str,
    ) -> Result<Option<WorkbenchSnapshotRow>, ReadModelRepositoryError>;

    async fn find_workbench_row(
        &self,
        row_id: Uuid,
        month: Option<&str>,
    ) -> Result<Option<WorkbenchRowDetailRow>, ReadModelRepositoryError>;

    async fn search_index_rows(
        &self,
        query: &str,
        entity_types: &[String],
        month: Option<&str>,
        project_name: Option<&str>,
        zone_hint: Option<&str>,
        limit: i64,
    ) -> Result<Vec<SearchIndexRow>, ReadModelRepositoryError>;
}

#[derive(Clone)]
pub struct SqlxReadModelRepository {
    pool: PgPool,
}

impl SqlxReadModelRepository {
    pub fn new(pool: PgPool) -> Self {
        Self { pool }
    }
}

#[async_trait]
impl ReadModelRepository for SqlxReadModelRepository {
    async fn find_workbench_snapshot(
        &self,
        month: &str,
    ) -> Result<Option<WorkbenchSnapshotRow>, ReadModelRepositoryError> {
        let row = sqlx::query(WORKBENCH_SNAPSHOT_SQL)
            .bind(format!("workbench:{month}"))
            .fetch_optional(&self.pool)
            .await?;

        row.map(row_to_workbench_snapshot).transpose()
    }

    async fn find_workbench_row(
        &self,
        row_id: Uuid,
        month: Option<&str>,
    ) -> Result<Option<WorkbenchRowDetailRow>, ReadModelRepositoryError> {
        let row = sqlx::query(WORKBENCH_ROW_DETAIL_SQL)
            .bind(row_id)
            .bind(month)
            .fetch_optional(&self.pool)
            .await?;

        row.map(row_to_workbench_row_detail).transpose()
    }

    async fn search_index_rows(
        &self,
        query: &str,
        entity_types: &[String],
        month: Option<&str>,
        project_name: Option<&str>,
        zone_hint: Option<&str>,
        limit: i64,
    ) -> Result<Vec<SearchIndexRow>, ReadModelRepositoryError> {
        let rows = sqlx::query(SEARCH_INDEX_SQL)
            .bind(query)
            .bind(month)
            .bind(entity_types)
            .bind(project_name)
            .bind(zone_hint)
            .bind(limit)
            .fetch_all(&self.pool)
            .await?;

        rows.into_iter().map(row_to_search_index).collect()
    }
}

const WORKBENCH_SNAPSHOT_SQL: &str = r#"
select
  scope_key,
  scope_type,
  to_char(scope_month, 'YYYY-MM-DD') as scope_month,
  schema_version,
  payload,
  ignored_rows,
  summary,
  source_versions,
  to_char(generated_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as generated_at,
  stale,
  case
    when stale then greatest(0, extract(epoch from now() - updated_at)::bigint)
    else 0
  end as stale_seconds,
  stale_reason,
  rebuild_task_id::text as rebuild_task_id,
  to_char(updated_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as updated_at
from read_model.workbench_snapshots
where scope_key = $1
  and scope_type = 'month'
"#;

const WORKBENCH_ROW_DETAIL_SQL: &str = r#"
select
  id::text as id,
  to_char(scope_month, 'YYYY-MM-DD') as scope_month,
  row_id::text as row_id,
  row_type,
  zone_hint,
  group_key,
  payload,
  source_versions,
  to_char(generated_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as generated_at,
  stale,
  case
    when stale then greatest(0, extract(epoch from now() - updated_at)::bigint)
    else 0
  end as stale_seconds,
  stale_reason,
  to_char(updated_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as updated_at
from read_model.workbench_rows
where row_id = $1
  and ($2::text is null or scope_month = to_date($2::text || '-01', 'YYYY-MM-DD'))
order by scope_month desc, updated_at desc
limit 1
"#;

const SEARCH_INDEX_SQL: &str = r#"
with candidate_months as (
  select to_date($2::text || '-01', 'YYYY-MM-DD') as scope_month
  where $2::text is not null
  union all
  select scope_month
  from (
    select distinct scope_month
    from read_model.search_index_rows
    where $2::text is null
    order by scope_month desc
    limit 12
  ) recent_months
)
select
  sir.id::text as id,
  sir.entity_type,
  sir.entity_id::text as entity_id,
  sir.source_kind,
  to_char(sir.scope_month, 'YYYY-MM-DD') as scope_month,
  sir.title,
  sir.subtitle,
  sir.amount::text as amount,
  sir.status,
  sir.zone_hint,
  sir.project_id,
  sir.project_name,
  sir.jump_target,
  sir.payload,
  sir.source_versions,
  to_char(sir.generated_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as generated_at,
  sir.stale,
  case
    when sir.stale then greatest(0, extract(epoch from now() - sir.updated_at)::bigint)
    else 0
  end as stale_seconds,
  sir.stale_reason,
  to_char(sir.updated_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as updated_at
from read_model.search_index_rows sir
join candidate_months on candidate_months.scope_month = sir.scope_month
where sir.searchable_text ilike ('%' || $1::text || '%')
  and sir.entity_type = any($3::text[])
  and ($4::text is null or sir.project_name ilike ('%' || $4::text || '%'))
  and ($5::text is null or sir.zone_hint = $5)
order by
  case when $2::text is null then sir.scope_month end desc,
  sir.stale asc,
  similarity(sir.searchable_text, $1::text) desc,
  sir.updated_at desc
limit $6
"#;

fn row_to_workbench_snapshot(
    row: sqlx::postgres::PgRow,
) -> Result<WorkbenchSnapshotRow, ReadModelRepositoryError> {
    Ok(WorkbenchSnapshotRow {
        scope_key: row.try_get("scope_key")?,
        scope_type: row.try_get("scope_type")?,
        scope_month: row.try_get("scope_month")?,
        schema_version: row.try_get("schema_version")?,
        payload: row.try_get("payload")?,
        ignored_rows: row.try_get("ignored_rows")?,
        summary: row.try_get("summary")?,
        source_versions: row.try_get("source_versions")?,
        generated_at: row.try_get("generated_at")?,
        stale: row.try_get("stale")?,
        stale_seconds: row.try_get("stale_seconds")?,
        stale_reason: row.try_get("stale_reason")?,
        rebuild_task_id: row.try_get("rebuild_task_id")?,
        updated_at: row.try_get("updated_at")?,
    })
}

fn row_to_workbench_row_detail(
    row: sqlx::postgres::PgRow,
) -> Result<WorkbenchRowDetailRow, ReadModelRepositoryError> {
    Ok(WorkbenchRowDetailRow {
        id: row.try_get("id")?,
        scope_month: row.try_get("scope_month")?,
        row_id: row.try_get("row_id")?,
        row_type: row.try_get("row_type")?,
        zone_hint: row.try_get("zone_hint")?,
        group_key: row.try_get("group_key")?,
        payload: row.try_get("payload")?,
        source_versions: row.try_get("source_versions")?,
        generated_at: row.try_get("generated_at")?,
        stale: row.try_get("stale")?,
        stale_seconds: row.try_get("stale_seconds")?,
        stale_reason: row.try_get("stale_reason")?,
        updated_at: row.try_get("updated_at")?,
    })
}

fn row_to_search_index(
    row: sqlx::postgres::PgRow,
) -> Result<SearchIndexRow, ReadModelRepositoryError> {
    Ok(SearchIndexRow {
        id: row.try_get("id")?,
        entity_type: row.try_get("entity_type")?,
        entity_id: row.try_get("entity_id")?,
        source_kind: row.try_get("source_kind")?,
        scope_month: row.try_get("scope_month")?,
        title: row.try_get("title")?,
        subtitle: row.try_get("subtitle")?,
        amount: row.try_get("amount")?,
        status: row.try_get("status")?,
        zone_hint: row.try_get("zone_hint")?,
        project_id: row.try_get("project_id")?,
        project_name: row.try_get("project_name")?,
        jump_target: row.try_get("jump_target")?,
        payload: row.try_get("payload")?,
        source_versions: row.try_get("source_versions")?,
        generated_at: row.try_get("generated_at")?,
        stale: row.try_get("stale")?,
        stale_seconds: row.try_get("stale_seconds")?,
        stale_reason: row.try_get("stale_reason")?,
        updated_at: row.try_get("updated_at")?,
    })
}
