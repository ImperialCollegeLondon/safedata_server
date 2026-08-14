"""Ingestion logic for updating the Gazetteer from an uploaded GeoJSON file."""

from typing import Any

from django.conf import settings
from django.contrib.gis.geos import GEOSGeometry

from .models import Gazetteer


class GazetteerIngestError(Exception):
    """Raised when a GeoJSON feature or file is malformed or fails validation."""


def ingest_gazetteer_entry(feature: dict[str, Any]) -> None:
    """Adds or edits a single Gazetteer row from one parsed GeoJSON Feature.

    Args:
        feature: A parsed GeoJSON Feature. Must have a "location" property
            (the site name) and a geometry.

    Raises:
        GazetteerIngestError: if the feature is missing a "location"
            property or a valid geometry.
    """
    location_name = _get_location_name(feature)
    geometry = _get_geometry(feature, location_name=location_name)

    local_geometry = geometry.transform(settings.GAZETTEER_LOCAL_EPSG, clone=True)

    Gazetteer.objects.update_or_create(
        location=location_name,
        defaults={
            "geom_wgs84": geometry,
            "geom_local": local_geometry,
        },
    )

def ingest_multiple_gazetteer_entries(geojson: dict[str, Any]) -> None:
    """Adds or edits Gazetteer rows from a parsed GeoJSON FeatureCollection.

    Args:
        geojson: A parsed GeoJSON FeatureCollection.

    Raises:
        GazetteerIngestError: if the file is not a valid FeatureCollection,
            or any feature fails ingestion.
    """
    if geojson.get("type") != "FeatureCollection":
        raise GazetteerIngestError(
            "Expected a GeoJSON FeatureCollection, got "
            f"{geojson.get('type', 'unknown')!r}."
        )

    features = geojson.get("features", [])
    if not features:
        raise GazetteerIngestError("FeatureCollection contains no features.")

    # Consider wrapping this in transation.atomic()? 
    for feature in features:
        ingest_gazetteer_entry(feature)


def _get_location_name(feature: dict[str, Any]) -> str:
    properties = feature.get("properties") or {}
    location_name = properties.get("location")

    if not location_name:
        raise GazetteerIngestError(
            "Feature is missing a 'location' property."
        )

    return location_name


def _get_geometry(feature: dict[str, Any], location_name: str) -> GEOSGeometry:
    geometry_data = feature.get("geometry")

    if not geometry_data:
        raise GazetteerIngestError(
            f"Feature '{location_name}' has no geometry."
        )

    try:
        # GeoJSON is always WGS84 by spec (RFC 7946), so this is always
        # SRID 4326 regardless of what the file's CRS member (if any) claims.
        geometry = GEOSGeometry(str(geometry_data).replace("'", '"'), srid=4326)
    except Exception as exc:
        raise GazetteerIngestError(
            f"Feature '{location_name}' has invalid geometry: {exc}"
        ) from exc

    return geometry