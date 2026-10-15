-- wgs84_to_gcj02: WGS-84 -> GCJ-02 coordinate conversion for the AMap (Gaode) dashboards.
--
-- The map panels call (wgs84_to_gcj02(latitude, longitude)).gcjLat / .gcjLon,
-- the same convention as hipudding's TeslaMate Grafana image (hipudding/grafana),
-- whose startup script creates these functions from its proc.sql. If you use
-- that image you already have them and do not need this script.
--
-- Otherwise run it once against the TeslaMate database. It creates exactly the
-- functions from hipudding's proc.sql (https://github.com/hipudding/teslamate,
-- branches *.amap), so hipudding/grafana can still take over later.
--
-- It stops without changing anything if a different wgs84_to_gcj02 exists that
-- it does not recognise, or that other database functions depend on.
\set ON_ERROR_STOP on
BEGIN;

DO $check$
DECLARE
    fn   oid;
    args text;
    src  text;
BEGIN
    -- name used briefly by an earlier version of this script
    DROP FUNCTION IF EXISTS amap_wgs84_to_gcj02(double precision, double precision);

    SELECT p.oid, pg_get_function_arguments(p.oid), p.prosrc INTO fn, args, src
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE p.proname = 'wgs84_to_gcj02'
      AND n.nspname = current_schema()
      AND p.proargtypes = '701 701'::oidvector;  -- (double precision, double precision)

    IF fn IS NULL OR args = 'wgslat double precision, wgslon double precision' THEN
        RETURN;  -- missing, or hipudding's: (re)create below
    END IF;

    -- another program's function calls it (e.g. a trigger): replacing it would break that program
    SELECT string_agg(p.proname, ', ') INTO src
    FROM pg_proc p
    WHERE p.oid <> fn AND p.prosrc ILIKE '%wgs84_to_gcj02%';
    IF src IS NOT NULL THEN
        RAISE EXCEPTION 'wgs84_to_gcj02(%) is used by other functions (%); nothing was changed', args, src;
    END IF;

    IF args IN ('lat double precision, lon double precision, OUT gcjlat double precision, OUT gcjlon double precision',
                'wgs_lon double precision, wgs_lat double precision, OUT gcj_lon double precision, OUT gcj_lat double precision') THEN
        RAISE NOTICE 'Replacing wgs84_to_gcj02 created by an earlier version of this script';
        DROP FUNCTION wgs84_to_gcj02(double precision, double precision);
    ELSE
        RAISE EXCEPTION 'An unknown wgs84_to_gcj02(%) exists; nothing was changed', args;
    END IF;
END
$check$;

-- ---- hipudding proc.sql (verbatim) ----
CREATE OR REPLACE FUNCTION transformLat(x DOUBLE PRECISION, y DOUBLE PRECISION)
RETURNS DOUBLE PRECISION AS '
DECLARE
    ret DOUBLE PRECISION;
BEGIN
    ret := -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * sqrt(abs(x));
    ret := ret + (20.0 * sin(6.0 * x * pi()) + 20.0 * sin(2.0 * x * pi())) * 2.0 / 3.0;
    ret := ret + (20.0 * sin(y * pi()) + 40.0 * sin(y / 3.0 * pi())) * 2.0 / 3.0;
    ret := ret + (160.0 * sin(y / 12.0 * pi()) + 320 * sin(y * pi() / 30.0)) * 2.0 / 3.0;
    RETURN ret;
END;
' LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION transformLon(x DOUBLE PRECISION, y DOUBLE PRECISION)
RETURNS DOUBLE PRECISION AS '
DECLARE
    ret DOUBLE PRECISION;
BEGIN
    ret := 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * sqrt(abs(x));
    ret := ret + (20.0 * sin(6.0 * x * pi()) + 20.0 * sin(2.0 * x * pi())) * 2.0 / 3.0;
    ret := ret + (20.0 * sin(x * pi()) + 40.0 * sin(x / 3.0 * pi())) * 2.0 / 3.0;
    ret := ret + (150.0 * sin(x / 12.0 * pi()) + 300.0 * sin(x / 30.0 * pi())) * 2.0 / 3.0;
    RETURN ret;
END;
' LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION delta(lat DOUBLE PRECISION, lon DOUBLE PRECISION)
RETURNS TABLE (dLat DOUBLE PRECISION, dLon DOUBLE PRECISION) AS '
DECLARE
    a CONSTANT DOUBLE PRECISION := 6378245.0;
    ee CONSTANT DOUBLE PRECISION := 0.00669342162296594323;
    radLat DOUBLE PRECISION;
    magic DOUBLE PRECISION;
    sqrtMagic DOUBLE PRECISION;
BEGIN
    radLat := lat / 180.0 * pi();
    magic := sin(radLat);
    magic := 1 - ee * magic * magic;
    sqrtMagic := sqrt(magic);
    
    dLat := transformLat(lon - 105.0, lat - 35.0);
    dLon := transformLon(lon - 105.0, lat - 35.0);
    
    dLat := (dLat * 180.0) / ((a * (1 - ee)) / (magic * sqrtMagic) * pi());
    dLon := (dLon * 180.0) / (a / sqrtMagic * cos(radLat) * pi());
    
    RETURN QUERY SELECT dLat, dLon;
END;
' LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION wgs84_to_gcj02(wgsLat DOUBLE PRECISION, wgsLon DOUBLE PRECISION)
RETURNS TABLE (gcjLat DOUBLE PRECISION, gcjLon DOUBLE PRECISION) AS '
DECLARE
    dLat DOUBLE PRECISION;
    dLon DOUBLE PRECISION;
BEGIN
    IF wgsLat < 0 OR wgsLat > 60.0 OR wgsLon < 72.004 OR wgsLon > 137.8347 THEN
        RETURN QUERY SELECT wgsLat, wgsLon;
    ELSE
        SELECT delta.dLat, delta.dLon INTO dLat, dLon FROM delta(wgsLat, wgsLon);
        SELECT wgsLat + dLat, wgsLon + dLon INTO gcjLat, gcjLon;
        RETURN QUERY SELECT gcjLat, gcjLon;
    END IF;
END;
' LANGUAGE plpgsql;
-- ---- end of hipudding proc.sql ----

COMMIT;
