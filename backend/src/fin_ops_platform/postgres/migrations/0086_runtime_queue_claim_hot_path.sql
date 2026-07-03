-- Runtime worker claim hot path.
--
-- `RuntimeQueueRepository.claim_next(...)` claims one event per worker lane and
-- almost always supplies an event_type filter. Keep the index partial to the
-- active queue and include the priority rank used by the claim ORDER BY so
-- grouped read-model smokes do not scan unrelated pending event types before
-- finding the lane-local next event.

create index if not exists outbox_events_claim_event_type_priority_idx
    on job.outbox_events (
        event_type,
        status,
        (
            case priority
                when 'urgent' then 3
                when 'high' then 2
                when 'normal' then 1
                else 0
            end
        ) desc,
        available_at,
        created_at,
        id
    )
    where status in ('pending', 'processing');
