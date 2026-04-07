-- fin-ops OA menu bootstrap
-- Use on the OA database after confirming parent menu id and order number.
-- Safe intent:
--   1. Reuse existing menu when perms = 'finops:app:view'
--   2. Otherwise insert a new menu row

SET @finops_parent_menu_id = 0;
SET @finops_order_num = 90;
SET @finops_menu_name = '财务运营平台';
SET @finops_menu_path = 'https://www.yn-sourcing.com/fin-ops/?embedded=oa';
SET @finops_menu_perms = 'finops:app:view';
SET @finops_menu_icon = 'money';
SET @finops_operator = 'finops_deploy';

SET @existing_finops_menu_id = (
  SELECT menu_id
  FROM sys_menu
  WHERE perms = @finops_menu_perms
  ORDER BY menu_id DESC
  LIMIT 1
);

UPDATE sys_menu
SET
  parent_id = @finops_parent_menu_id,
  menu_name = @finops_menu_name,
  order_num = @finops_order_num,
  path = @finops_menu_path,
  component = '',
  `query` = '',
  is_frame = '1',
  is_cache = '1',
  is_blank = '1',
  menu_type = 'C',
  visible = '0',
  status = '0',
  icon = @finops_menu_icon,
  remark = 'fin-ops iframe menu',
  update_by = @finops_operator,
  update_time = SYSDATE()
WHERE menu_id = @existing_finops_menu_id;

INSERT INTO sys_menu (
  parent_id,
  menu_name,
  order_num,
  path,
  component,
  `query`,
  is_frame,
  is_cache,
  is_blank,
  menu_type,
  visible,
  status,
  perms,
  icon,
  remark,
  create_by,
  create_time
)
SELECT
  @finops_parent_menu_id,
  @finops_menu_name,
  @finops_order_num,
  @finops_menu_path,
  '',
  '',
  '1',
  '1',
  '1',
  'C',
  '0',
  '0',
  @finops_menu_perms,
  @finops_menu_icon,
  'fin-ops iframe menu',
  @finops_operator,
  SYSDATE()
WHERE @existing_finops_menu_id IS NULL;

SELECT
  menu_id,
  parent_id,
  menu_name,
  path,
  perms,
  is_frame,
  is_blank,
  menu_type,
  visible,
  status
FROM sys_menu
WHERE perms = @finops_menu_perms;
