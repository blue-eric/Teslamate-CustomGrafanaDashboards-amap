-- WGS-84 -> GCJ-02 coordinate conversion for the AMap (Gaode) based dashboards.
-- TeslaMate stores positions in WGS-84, while AMap tiles use GCJ-02, so the
-- map panels in CurrentChargeView, CurrentDriveView, CurrentState and
-- TrackingDrives call this function. Run it once against the TeslaMate database.
-- Coordinates outside mainland China are returned unchanged.

-- Remove older versions of the function first (for example one taking numeric
-- arguments or returning an anonymous record): PostgreSQL would otherwise pick
-- that overload for the numeric latitude/longitude columns and the dashboards
-- fail with: could not identify column "gcjlat" in record data type.
DO $$
DECLARE
    f regprocedure;
BEGIN
    FOR f IN
        SELECT p.oid::regprocedure
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE p.proname = 'wgs84_to_gcj02' AND n.nspname = current_schema()
    LOOP
        EXECUTE 'DROP FUNCTION ' || f;
    END LOOP;
END
$$;

CREATE FUNCTION wgs84_to_gcj02(
    lat double precision,
    lon double precision,
    OUT gcjLat double precision,
    OUT gcjLon double precision
)
LANGUAGE plpgsql IMMUTABLE STRICT PARALLEL SAFE
AS $$
DECLARE
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
    IF lon < 72.004 OR lon > 137.8347 OR lat < 0.8293 OR lat > 55.8271 THEN
        gcjLat := lat;
        gcjLon := lon;
        RETURN;
    END IF;

    x := lon - 105.0;
    y := lat - 35.0;

    dlat := -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * sqrt(abs(x))
          + (20.0 * sin(6.0 * x * pi()) + 20.0 * sin(2.0 * x * pi())) * 2.0 / 3.0
          + (20.0 * sin(y * pi()) + 40.0 * sin(y / 3.0 * pi())) * 2.0 / 3.0
          + (160.0 * sin(y / 12.0 * pi()) + 320.0 * sin(y * pi() / 30.0)) * 2.0 / 3.0;

    dlon := 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * sqrt(abs(x))
          + (20.0 * sin(6.0 * x * pi()) + 20.0 * sin(2.0 * x * pi())) * 2.0 / 3.0
          + (20.0 * sin(x * pi()) + 40.0 * sin(x / 3.0 * pi())) * 2.0 / 3.0
          + (150.0 * sin(x / 12.0 * pi()) + 300.0 * sin(x / 30.0 * pi())) * 2.0 / 3.0;

    radlat := lat / 180.0 * pi();
    magic := 1 - ee * sin(radlat) * sin(radlat);
    sqrtmagic := sqrt(magic);

    dlat := (dlat * 180.0) / ((a * (1 - ee)) / (magic * sqrtmagic) * pi());
    dlon := (dlon * 180.0) / (a / sqrtmagic * cos(radlat) * pi());

    gcjLat := lat + dlat;
    gcjLon := lon + dlon;
END;
$$;
