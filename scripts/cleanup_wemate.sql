-- 清理 wemate 在 TeslaMate 数据库中留下的触发器、函数和表（必做部分）
-- 执行前请先停掉 teslamate 和 grafana，并做好备份。全部在一个事务里，任何一步出错都会整体回滚。
\set ON_ERROR_STOP on
BEGIN;

-- 安全检查：数据库里的 wgs84_to_gcj02 必须是 wemate 的版本（带 v20251120_high_precision 标记）或不存在，否则中止
DO $$
DECLARE src text;
BEGIN
    SELECT p.prosrc INTO src FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'public' AND p.proname = 'wgs84_to_gcj02' AND p.proargtypes = '701 701'::oidvector;
    IF src IS NOT NULL AND src NOT LIKE '%v20251120_high_precision%' THEN
        RAISE EXCEPTION '数据库里的 wgs84_to_gcj02 不是 wemate 的版本，已中止，未做任何修改';
    END IF;
END $$;

-- 1. 先删触发器（顺序很重要：必须先于函数删除，否则 TeslaMate 写入轨迹点会失败）
DROP TRIGGER IF EXISTS positions_gcj02_fill_trg ON positions;
DROP TRIGGER IF EXISTS drive_update_trigger ON drives;
DROP TRIGGER IF EXISTS charging_update_trigger ON charging_processes;

-- 2. 再删触发器用的函数
DROP FUNCTION IF EXISTS positions_gcj02_fill();
DROP FUNCTION IF EXISTS notify_drive_update();
DROP FUNCTION IF EXISTS notify_charging_update();

-- 3. 删除 wemate 版的坐标转换函数（Grafana 重启时 hipudding 会重建它自己的版本）
DROP FUNCTION IF EXISTS wgs84_to_gcj02(double precision, double precision);

-- 4. 删除 wemate 的进度表
DROP TABLE IF EXISTS gcj02_migration_state;
DROP TABLE IF EXISTS _flags;

COMMIT;
\echo 'cleanup_wemate.sql 完成'
