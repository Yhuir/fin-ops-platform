set local lock_timeout = '10s';
set local statement_timeout = '5min';

create index if not exists workbench_oa_supporting_documents_gallery_idx
    on app.workbench_oa_supporting_documents (created_at desc, id desc)
    where status = 'active';
