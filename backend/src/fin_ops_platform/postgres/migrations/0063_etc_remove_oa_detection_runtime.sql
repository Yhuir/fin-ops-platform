update app.etc_business_batches
set
    status = 'oa_confirmation_pending',
    oa_detection_status = null,
    oa_detection_payload = '{}'::jsonb,
    raw_payload = (
        jsonb_set(
            coalesce(raw_payload, '{}'::jsonb),
            '{normalized_payload,status}',
            to_jsonb('oa_confirmation_pending'::text),
            true
        )
        #- '{normalized_payload,oa_detection_status}'
        #- '{normalized_payload,oa_detection_started_at}'
        #- '{normalized_payload,oa_detection_next_run_at}'
        #- '{normalized_payload,oa_detection_deadline_at}'
        #- '{normalized_payload,oa_detection_final_retry_until}'
        #- '{normalized_payload,oa_detection_attempts}'
        #- '{normalized_payload,oa_detection_error}'
        #- '{normalized_payload,oa_detection_reason}'
    ),
    updated_at = now()
where status in (
    'oa_submission_detecting',
    'oa_detection_timeout',
    'oa_detection_conflict',
    'oa_detection_unavailable'
);
