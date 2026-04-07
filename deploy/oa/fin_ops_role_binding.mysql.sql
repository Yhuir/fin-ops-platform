-- fin-ops role binding bootstrap
-- Use after fin_ops_menu.mysql.sql has created or updated the menu.
-- Replace @target_role_key with the OA role that should see fin-ops.

SET @finops_menu_perms = 'finops:app:view';
SET @target_role_key = 'finance';

SET @finops_menu_id = (
  SELECT menu_id
  FROM sys_menu
  WHERE perms = @finops_menu_perms
  ORDER BY menu_id DESC
  LIMIT 1
);

SET @target_role_id = (
  SELECT role_id
  FROM sys_role
  WHERE role_key = @target_role_key
  ORDER BY role_id DESC
  LIMIT 1
);

INSERT INTO sys_role_menu (role_id, menu_id)
SELECT @target_role_id, @finops_menu_id
WHERE @target_role_id IS NOT NULL
  AND @finops_menu_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1
    FROM sys_role_menu
    WHERE role_id = @target_role_id
      AND menu_id = @finops_menu_id
  );

SELECT
  r.role_id,
  r.role_name,
  r.role_key,
  m.menu_id,
  m.menu_name,
  m.perms
FROM sys_role_menu rm
JOIN sys_role r ON r.role_id = rm.role_id
JOIN sys_menu m ON m.menu_id = rm.menu_id
WHERE m.perms = @finops_menu_perms
ORDER BY r.role_id;
