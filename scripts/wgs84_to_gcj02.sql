-- WGS-84 -> GCJ-02 coordinate conversion for the AMap (Gaode) based dashboards.
-- TeslaMate stores positions in WGS-84, while AMap tiles use GCJ-02, so the
-- map panels in CurrentChargeView, CurrentDriveView, CurrentState and
-- TrackingDrives call:
--
--     (wgs84_to_gcj02(longitude, latitude)).gcj_lon / .gcj_lat
--
-- This is the same function that hipudding's TeslaMate tools
-- (hipudding/grafana, hipudding/teslamate_fix_addrs) create and maintain.
-- If you run those tools you already have it and this script changes nothing.
-- Otherwise it creates the function with the same signature and algorithm,
-- so it stays compatible if you install those tools later.
--
-- The script never replaces an existing function, except one created by an
-- earlier version of this script (arguments in latitude, longitude order,
-- results named gcjlat/gcjlon), which the dashboards no longer use.
-- Coordinates outside mainland China are returned unchanged.

DO $do$
DECLARE
    args text;
BEGIN
    -- Function name used briefly by an earlier version of this script.
    DROP FUNCTION IF EXISTS amap_wgs84_to_gcj02(double precision, double precision);

    SELECT pg_get_function_arguments(p.oid) INTO args
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE p.proname = 'wgs84_to_gcj02'
      AND n.nspname = current_schema()
      AND p.proargtypes = '701 701'::oidvector;  -- (double precision, double precision)

    IF args = 'lat double precision, lon double precision, OUT gcjlat double precision, OUT gcjlon double precision' THEN
        RAISE NOTICE 'Replacing wgs84_to_gcj02 from an earlier version of this script';
        DROP FUNCTION wgs84_to_gcj02(double precision, double precision);
        args := NULL;
    END IF;

    IF args IS NOT NULL THEN
        IF args = 'wgs_lon double precision, wgs_lat double precision, OUT gcj_lon double precision, OUT gcj_lat double precision' THEN
            RAISE NOTICE 'wgs84_to_gcj02 already exists, nothing to do';
        ELSE
            RAISE WARNING 'A different wgs84_to_gcj02(%) already exists and was left unchanged; the map panels need (wgs_lon, wgs_lat) -> (gcj_lon, gcj_lat)', args;
        END IF;
        RETURN;
    END IF;

    EXECUTE $create$
    CREATE FUNCTION wgs84_to_gcj02(
        wgs_lon double precision,
        wgs_lat double precision,
        OUT gcj_lon double precision,
        OUT gcj_lat double precision
    )
    LANGUAGE plpgsql IMMUTABLE STRICT PARALLEL SAFE
    AS $fn$
    DECLARE
        pi CONSTANT double precision := 3.1415926535897932384626;
        a  CONSTANT double precision := 6378245.0;
        ee CONSTANT double precision := 0.00669342162296594323;
        x double precision;
        y double precision;
        dlat double precision;
        dlon double precision;
        radlat double precision;
        magic double precision;
        sqrtmagic double precision;
    BEGIN
        IF NOT (wgs_lon BETWEEN 72.004 AND 137.8347 AND wgs_lat BETWEEN 0.8293 AND 55.8271) THEN
            gcj_lon := wgs_lon;
            gcj_lat := wgs_lat;
            RETURN;
        END IF;

        x := wgs_lon - 105.0;
        y := wgs_lat - 35.0;

        dlat := -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * sqrt(abs(x));
        dlat := dlat + (20.0 * sin(6.0 * x * pi) + 20.0 * sin(2.0 * x * pi)) * 2.0 / 3.0;
        dlat := dlat + (20.0 * sin(y * pi) + 40.0 * sin(y / 3.0 * pi)) * 2.0 / 3.0;
        dlat := dlat + (160.0 * sin(y / 12.0 * pi) + 320.0 * sin(y * pi / 30.0)) * 2.0 / 3.0;

        dlon := 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * sqrt(abs(x));
        dlon := dlon + (20.0 * sin(6.0 * x * pi) + 20.0 * sin(2.0 * x * pi)) * 2.0 / 3.0;
        dlon := dlon + (20.0 * sin(x * pi) + 40.0 * sin(x / 3.0 * pi)) * 2.0 / 3.0;
        dlon := dlon + (150.0 * sin(x / 12.0 * pi) + 300.0 * sin(x / 30.0 * pi)) * 2.0 / 3.0;

        radlat := wgs_lat * (pi / 180.0);
        magic := sin(radlat);
        magic := 1 - ee * magic * magic;
        sqrtmagic := sqrt(magic);

        dlat := (dlat * 180.0) / ((a * (1 - ee)) / (magic * sqrtmagic) * pi);
        dlon := (dlon * 180.0) / (a / sqrtmagic * cos(radlat) * pi);

        gcj_lat := wgs_lat + dlat;
        gcj_lon := wgs_lon + dlon;
    END;
    $fn$
    $create$;
    RAISE NOTICE 'Created wgs84_to_gcj02';
END
$do$;
