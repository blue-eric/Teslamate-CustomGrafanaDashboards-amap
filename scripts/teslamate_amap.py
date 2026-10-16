"""Switch the map panels of TeslaMate's own dashboards to AMap (Gaode).

Used by build_i18n.py for the dashboards in teslamate/source/. Every geomap
panel gets the AMap basemap, and its queries are wrapped instead of edited:

    SELECT q.*, g.gcjlat AS amap_latitude, g.gcjlon AS amap_longitude
    FROM (<original query>) q
    CROSS JOIN LATERAL wgs84_to_gcj02(q.latitude::float8, q.longitude::float8) g

An organize transformation then drops the original latitude/longitude and
renames the converted columns back, so the map layers keep working with the
field names they already use. This works whatever the original query looks
like, as long as it returns columns named latitude and longitude, so new
TeslaMate releases need no manual changes. The conversion runs on the rows
the query returns (usually already aggregated), once per row.
"""

import copy

AMAP_BASEMAP = {
    "config": {
        "url": "https://webrd0{1-4}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}",
        "attribution": "© 高德地图",
    },
    "name": "Layer 0",
    "type": "xyz",
}
MARK = "-- amap: WGS-84 -> GCJ-02 (scripts/teslamate_amap.py)"
ORGANIZE = {
    "id": "organize",
    "options": {
        "excludeByName": {"latitude": True, "longitude": True},
        "renameByName": {"amap_latitude": "latitude", "amap_longitude": "longitude"},
    },
}


def wrap_sql(sql):
    if MARK in sql:
        return sql
    body = sql.rstrip().rstrip(";").rstrip()
    return (f"{MARK}\n"
            "SELECT q.*, g.gcjlat AS amap_latitude, g.gcjlon AS amap_longitude\n"
            f"FROM (\n{body}\n) q\n"
            "CROSS JOIN LATERAL wgs84_to_gcj02(q.latitude::float8, q.longitude::float8) g")


def iter_panels(panels):
    for panel in panels or []:
        yield panel
        yield from iter_panels(panel.get("panels"))


def amapify(dashboard, problems):
    """Convert the geomap panels in place; returns how many were converted."""
    count = 0
    for panel in iter_panels(dashboard.get("panels")):
        if panel.get("type") != "geomap":
            continue
        targets = [t for t in panel.get("targets") or [] if t.get("rawSql")]
        if not targets:
            problems.append(f"{dashboard.get('uid')}: map panel {panel.get('title')!r} has no SQL query, left on OpenStreetMap")
            continue
        for target in targets:
            sql = target["rawSql"]
            if "latitude" not in sql or "longitude" not in sql:
                problems.append(f"{dashboard.get('uid')}: map panel {panel.get('title')!r} query has no latitude/longitude columns")
            target["rawSql"] = wrap_sql(sql)
        panel.setdefault("options", {})["basemap"] = copy.deepcopy(AMAP_BASEMAP)
        transformations = panel.get("transformations") or []
        if not any(t.get("options") == ORGANIZE["options"] for t in transformations):
            panel["transformations"] = [copy.deepcopy(ORGANIZE)] + transformations
        count += 1
    return count
