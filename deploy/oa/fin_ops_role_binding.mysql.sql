-- fin-ops fixed-menu role binding bootstrap / exact cleanup / rollback.
-- cleanup and rollback inputs are injected by root-owned deploy-control from the
-- approved settings access-control artifact. Missing or drifted inputs write zero rows.

SET @finops_menu_perms = 'finops:app:view';
SET @readonly_role_key = 'finops_read_export';
SET @full_access_role_key = 'finops_full_access';
SET @admin_role_key = 'finops_admin';
SET @finops_operation = COALESCE(@finops_operation, 'bootstrap');
SET @artifact_salt = COALESCE(@artifact_salt, '');
SET @approved_target_hashes_csv = COALESCE(@approved_target_hashes_csv, '');
SET @approved_target_count = COALESCE(@approved_target_count, 0);
SET @approved_target_set_sha256 = COALESCE(@approved_target_set_sha256, '');
SET @approved_before_sha256 = COALESCE(@approved_before_sha256, '');
SET @approved_after_sha256 = COALESCE(@approved_after_sha256, '');
SET SESSION group_concat_max_len = 16777216;

START TRANSACTION;

-- Lock the mutation surface before comparing the approved before-image.
SELECT COUNT(*) INTO @locked_binding_count FROM sys_role_menu FOR UPDATE;
SELECT COUNT(*) INTO @finops_menu_count
FROM sys_menu WHERE perms = @finops_menu_perms FOR UPDATE;
SELECT COUNT(*) INTO @dedicated_role_count
FROM sys_role
WHERE role_key IN (@readonly_role_key, @full_access_role_key, @admin_role_key)
FOR UPDATE;

SET @finops_menu_id = IF(
  @finops_menu_count = 1,
  (SELECT MIN(menu_id) FROM sys_menu WHERE perms = @finops_menu_perms),
  NULL
);
SET @readonly_role_count = (
  SELECT COUNT(*) FROM sys_role WHERE role_key = @readonly_role_key
);
SET @full_access_role_count = (
  SELECT COUNT(*) FROM sys_role WHERE role_key = @full_access_role_key
);
SET @admin_role_count = (
  SELECT COUNT(*) FROM sys_role WHERE role_key = @admin_role_key
);
SET @readonly_role_id = IF(
  @readonly_role_count = 1,
  (SELECT MIN(role_id) FROM sys_role WHERE role_key = @readonly_role_key),
  NULL
);
SET @full_access_role_id = IF(
  @full_access_role_count = 1,
  (SELECT MIN(role_id) FROM sys_role WHERE role_key = @full_access_role_key),
  NULL
);
SET @admin_role_id = IF(
  @admin_role_count = 1,
  (SELECT MIN(role_id) FROM sys_role WHERE role_key = @admin_role_key),
  NULL
);
SET @inventory_exact = (
  @finops_menu_count = 1
  AND @readonly_role_count = 1
  AND @full_access_role_count = 1
  AND @admin_role_count = 1
  AND @dedicated_role_count = 3
  AND @readonly_role_id <> @full_access_role_id
  AND @readonly_role_id <> @admin_role_id
  AND @full_access_role_id <> @admin_role_id
);
SET @dedicated_binding_count = (
  SELECT COUNT(*)
  FROM sys_role_menu
  WHERE menu_id = @finops_menu_id
    AND role_id IN (@readonly_role_id, @full_access_role_id, @admin_role_id)
);

DROP TEMPORARY TABLE IF EXISTS finops_exact_binding_targets;
CREATE TEMPORARY TABLE finops_exact_binding_targets (
  role_id BIGINT NOT NULL,
  menu_id BIGINT NOT NULL,
  target_sha256 CHAR(64) NOT NULL,
  PRIMARY KEY (role_id, menu_id),
  UNIQUE KEY uq_finops_exact_binding_target_hash (target_sha256)
) ENGINE=MEMORY;

INSERT INTO finops_exact_binding_targets (role_id, menu_id, target_sha256)
SELECT
  r.role_id,
  @finops_menu_id,
  SHA2(
    CONCAT(
      @artifact_salt,
      CHAR(0),
      'role_menu',
      CHAR(0),
      CAST(r.role_id AS CHAR),
      CHAR(0),
      CAST(@finops_menu_id AS CHAR)
    ),
    256
  )
FROM sys_role r
WHERE @finops_operation IN ('cleanup', 'rollback')
  AND @finops_menu_id IS NOT NULL
  AND r.role_key NOT IN (@readonly_role_key, @full_access_role_key, @admin_role_key)
  AND FIND_IN_SET(
    SHA2(
      CONCAT(
        @artifact_salt,
        CHAR(0),
        'role_menu',
        CHAR(0),
        CAST(r.role_id AS CHAR),
        CHAR(0),
        CAST(@finops_menu_id AS CHAR)
      ),
      256
    ),
    @approved_target_hashes_csv
  ) > 0;

SET @staged_target_count = (SELECT COUNT(*) FROM finops_exact_binding_targets);
SET @staged_target_set_sha256 = (
  SELECT SHA2(COALESCE(GROUP_CONCAT(target_sha256 ORDER BY target_sha256 SEPARATOR '\n'), ''), 256)
  FROM finops_exact_binding_targets
);
SET @current_target_count = (
  SELECT COUNT(*)
  FROM sys_role_menu rm
  JOIN finops_exact_binding_targets target
    ON target.role_id = rm.role_id AND target.menu_id = rm.menu_id
);
SET @current_before_sha256 = (
  SELECT SHA2(COALESCE(GROUP_CONCAT(binding_sha256 ORDER BY binding_sha256 SEPARATOR '\n'), ''), 256)
  FROM (
    SELECT SHA2(
      CONCAT(
        @artifact_salt,
        CHAR(0),
        'role_menu',
        CHAR(0),
        CAST(rm.role_id AS CHAR),
        CHAR(0),
        CAST(rm.menu_id AS CHAR)
      ),
      256
    ) AS binding_sha256
    FROM sys_role_menu rm
    WHERE rm.menu_id = @finops_menu_id
  ) current_bindings
);
SET @non_target_before_sha256 = (
  SELECT SHA2(COALESCE(GROUP_CONCAT(binding_sha256 ORDER BY binding_sha256 SEPARATOR '\n'), ''), 256)
  FROM (
    SELECT SHA2(CONCAT(CAST(rm.role_id AS CHAR), ':', CAST(rm.menu_id AS CHAR)), 256) AS binding_sha256
    FROM sys_role_menu rm
    LEFT JOIN finops_exact_binding_targets target
      ON target.role_id = rm.role_id AND target.menu_id = rm.menu_id
    WHERE target.role_id IS NULL
  ) non_target_bindings
);

SET @cleanup_preconditions_ok = (
  @finops_operation = 'cleanup'
  AND @inventory_exact
  AND @dedicated_binding_count = 3
  AND @artifact_salt <> ''
  AND @approved_target_count > 0
  AND @staged_target_count = @approved_target_count
  AND @current_target_count = @approved_target_count
  AND @staged_target_set_sha256 = @approved_target_set_sha256
  AND @current_before_sha256 = @approved_before_sha256
);
SET @rollback_preconditions_ok = (
  @finops_operation = 'rollback'
  AND @inventory_exact
  AND @dedicated_binding_count = 3
  AND @artifact_salt <> ''
  AND @approved_target_count > 0
  AND @staged_target_count = @approved_target_count
  AND @current_target_count = 0
  AND @staged_target_set_sha256 = @approved_target_set_sha256
  AND @current_before_sha256 = @approved_after_sha256
);

-- Bootstrap remains dedicated-role-only and refuses duplicate menu/role selectors.
INSERT INTO sys_role_menu (role_id, menu_id)
SELECT dedicated.role_id, @finops_menu_id
FROM (
  SELECT @readonly_role_id AS role_id
  UNION ALL SELECT @full_access_role_id
  UNION ALL SELECT @admin_role_id
) dedicated
WHERE @finops_operation = 'bootstrap'
  AND @inventory_exact
  AND NOT EXISTS (
    SELECT 1 FROM sys_role_menu rm
    WHERE rm.role_id = dedicated.role_id AND rm.menu_id = @finops_menu_id
  );

DELETE rm FROM sys_role_menu rm
JOIN finops_exact_binding_targets target
  ON target.role_id = rm.role_id AND target.menu_id = rm.menu_id
WHERE @cleanup_preconditions_ok;
SET @cleanup_affected_rows = IF(@finops_operation = 'cleanup', ROW_COUNT(), 0);

INSERT INTO sys_role_menu (role_id, menu_id)
SELECT target.role_id, target.menu_id
FROM finops_exact_binding_targets target
WHERE @rollback_preconditions_ok
  AND NOT EXISTS (
    SELECT 1 FROM sys_role_menu rm
    WHERE rm.role_id = target.role_id AND rm.menu_id = target.menu_id
  );
SET @rollback_affected_rows = IF(@finops_operation = 'rollback', ROW_COUNT(), 0);

SET @current_after_sha256 = (
  SELECT SHA2(COALESCE(GROUP_CONCAT(binding_sha256 ORDER BY binding_sha256 SEPARATOR '\n'), ''), 256)
  FROM (
    SELECT SHA2(
      CONCAT(
        @artifact_salt,
        CHAR(0),
        'role_menu',
        CHAR(0),
        CAST(rm.role_id AS CHAR),
        CHAR(0),
        CAST(rm.menu_id AS CHAR)
      ),
      256
    ) AS binding_sha256
    FROM sys_role_menu rm
    WHERE rm.menu_id = @finops_menu_id
  ) current_bindings
);
SET @non_target_after_sha256 = (
  SELECT SHA2(COALESCE(GROUP_CONCAT(binding_sha256 ORDER BY binding_sha256 SEPARATOR '\n'), ''), 256)
  FROM (
    SELECT SHA2(CONCAT(CAST(rm.role_id AS CHAR), ':', CAST(rm.menu_id AS CHAR)), 256) AS binding_sha256
    FROM sys_role_menu rm
    LEFT JOIN finops_exact_binding_targets target
      ON target.role_id = rm.role_id AND target.menu_id = rm.menu_id
    WHERE target.role_id IS NULL
  ) non_target_bindings
);
SET @cleanup_readback_ok = (
  @cleanup_preconditions_ok
  AND @cleanup_affected_rows = @approved_target_count
  AND @current_after_sha256 = @approved_after_sha256
  AND @non_target_before_sha256 = @non_target_after_sha256
);
SET @rollback_readback_ok = (
  @rollback_preconditions_ok
  AND @rollback_affected_rows = @approved_target_count
  AND @current_after_sha256 = @approved_before_sha256
  AND @non_target_before_sha256 = @non_target_after_sha256
);
SET @operation_readback_ok = (
  (@finops_operation = 'bootstrap' AND @inventory_exact)
  OR (@finops_operation = 'cleanup' AND @cleanup_readback_ok)
  OR (@finops_operation = 'rollback' AND @rollback_readback_ok)
);
SET @finish_statement = IF(@operation_readback_ok, 'COMMIT', 'ROLLBACK');
PREPARE finops_finish FROM @finish_statement;
EXECUTE finops_finish;
DEALLOCATE PREPARE finops_finish;

SELECT JSON_OBJECT(
  'operation', @finops_operation,
  'committed', @operation_readback_ok,
  'cleanup_readback_ok', @cleanup_readback_ok,
  'rollback_readback_ok', @rollback_readback_ok,
  'target_count', @approved_target_count,
  'affected_rows', IF(@finops_operation = 'cleanup', @cleanup_affected_rows, @rollback_affected_rows),
  'before_sha256', @current_before_sha256,
  'after_sha256', @current_after_sha256,
  'non_target_unchanged', @non_target_before_sha256 = @non_target_after_sha256
) AS finops_role_binding_result;
