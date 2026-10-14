-- 删除 wemate 加在 TeslaMate 表上的列（可选）
-- 只有确认 Grafana 里没有在用 wemate 的仪表板时才执行。必须在 cleanup_wemate.sql 之后执行。
\set ON_ERROR_STOP on
BEGIN;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'positions_gcj02_fill_trg') THEN
        RAISE EXCEPTION '请先执行 cleanup_wemate.sql（触发器 positions_gcj02_fill_trg 仍然存在），已中止';
    END IF;
END $$;
ALTER TABLE positions DROP COLUMN IF EXISTS gcj_lat, DROP COLUMN IF EXISTS gcj_lon;
ALTER TABLE geofences DROP COLUMN IF EXISTS time_prices;
COMMIT;
\echo 'cleanup_wemate_columns.sql 完成'
