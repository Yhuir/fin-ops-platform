alter table app.oa_applicant_credentials
    add column oa_user_id text,
    add column remark text not null default '',
    add column verified_at timestamptz,
    add column version integer not null default 1;

create unique index oa_applicant_credentials_oa_user_uidx
    on app.oa_applicant_credentials(oa_user_id) where oa_user_id is not null;

alter table app.oa_applicant_credentials
    add constraint oa_applicant_credentials_version_chk check (version > 0),
    add constraint oa_applicant_credentials_verified_identity_chk
        check (verified_at is null or oa_user_id is not null);
