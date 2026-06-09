update app.etc_business_batches
set
    oa_detection_status = null,
    oa_detection_payload = '{}'::jsonb,
    raw_payload = (
        coalesce(raw_payload, '{}'::jsonb)
        #- '{normalized_payload,oa_detection_status}'
        #- '{normalized_payload,oa_detection_started_at}'
        #- '{normalized_payload,oa_detection_next_run_at}'
        #- '{normalized_payload,oa_detection_deadline_at}'
        #- '{normalized_payload,oa_detection_final_retry_until}'
        #- '{normalized_payload,oa_detection_attempts}'
        #- '{normalized_payload,oa_detection_error}'
        #- '{normalized_payload,oa_detection_reason}'
    )
where oa_detection_status is not null
   or coalesce(oa_detection_payload, '{}'::jsonb) <> '{}'::jsonb
   or coalesce(raw_payload, '{}'::jsonb)->'normalized_payload' ?| array[
        'oa_detection_status',
        'oa_detection_started_at',
        'oa_detection_next_run_at',
        'oa_detection_deadline_at',
        'oa_detection_final_retry_until',
        'oa_detection_attempts',
        'oa_detection_error',
        'oa_detection_reason'
   ];
