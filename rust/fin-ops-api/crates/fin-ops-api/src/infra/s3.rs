use async_trait::async_trait;
use aws_config::BehaviorVersion;
use aws_sdk_s3::{
    config::Builder as S3ConfigBuilder, presigning::PresigningConfig, Client as AwsS3Client,
};
use aws_types::region::Region;

use crate::{
    config::S3Config,
    services::import_files::{
        FileObjectAccessError, FileObjectAccessGrant, FileObjectAccessProvider,
    },
};

const DEFAULT_REGION: &str = "us-east-1";

#[derive(Clone)]
pub struct S3Client {
    endpoint: Option<String>,
    bucket: Option<String>,
    region: String,
    presign_ttl: std::time::Duration,
}

impl S3Client {
    pub fn from_config(config: &S3Config) -> Self {
        Self {
            endpoint: config.endpoint.clone(),
            bucket: config.bucket.clone(),
            region: config
                .region
                .clone()
                .unwrap_or_else(|| DEFAULT_REGION.to_owned()),
            presign_ttl: config.presign_ttl,
        }
    }

    pub fn configured(&self) -> bool {
        self.bucket
            .as_deref()
            .map(|bucket| !bucket.trim().is_empty())
            .unwrap_or(false)
    }

    async fn client(&self) -> AwsS3Client {
        let shared_config = aws_config::defaults(BehaviorVersion::latest())
            .region(Region::new(self.region.clone()))
            .load()
            .await;
        let mut builder = S3ConfigBuilder::from(&shared_config);
        if let Some(endpoint) = self.endpoint.as_deref() {
            builder = builder.endpoint_url(endpoint).force_path_style(true);
        }
        AwsS3Client::from_conf(builder.build())
    }
}

#[async_trait]
impl FileObjectAccessProvider for S3Client {
    async fn presign_get_object(
        &self,
        bucket: &str,
        object_key: &str,
        object_version: Option<&str>,
    ) -> Result<FileObjectAccessGrant, FileObjectAccessError> {
        let configured_bucket = self
            .bucket
            .as_deref()
            .ok_or(FileObjectAccessError::NotConfigured)?;
        if configured_bucket != bucket {
            return Err(FileObjectAccessError::BucketNotAllowed);
        }

        let client = self.client().await;
        let mut request = client.get_object().bucket(bucket).key(object_key);
        if let Some(version_id) = object_version.filter(|value| !value.trim().is_empty()) {
            request = request.version_id(version_id);
        }
        let presigned = request
            .presigned(
                PresigningConfig::expires_in(self.presign_ttl)
                    .map_err(|error| FileObjectAccessError::PresignFailed(error.to_string()))?,
            )
            .await
            .map_err(|error| FileObjectAccessError::PresignFailed(error.to_string()))?;

        Ok(FileObjectAccessGrant {
            method: "presigned_get".to_owned(),
            url: presigned.uri().to_string(),
            ttl_seconds: self.presign_ttl.as_secs(),
            expires_at_unix_seconds: None,
        })
    }
}
