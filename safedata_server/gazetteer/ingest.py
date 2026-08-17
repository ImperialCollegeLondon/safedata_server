"""Ingestion logic for updating the Gazetteer from an uploaded GeoJSON file."""

import csv
from io import TextIOBase
from typing import Any

from django.conf import settings
from django.contrib.gis.geos import GEOSGeometry
from django.db import transaction

from .models import Gazetteer, GazetteerAlias


class GazetteerIngestError(Exception):
    """Raised when a GeoJSON feature or file is malformed or fails validation."""

class GazetteerAliasIngestError(Exception):
    """Raised when a gazetteer alias row or file is malformed or fails validation."""

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

    # Wrap this in a transaction so that if any of the locations fail, no
    # entries are added and the user can fix that entry in their json file
    # and re-upload the whole file.
    with transaction.atomic():
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


def ingest_gazetteer_alias_row(row: dict[str, str]) -> None:
    """Adds or edits a single GazetteerAlias row from one parsed CSV row.

    Args:
        row: A CSV row as a dict with keys "zenodo_record_id", "location",
            and "alias". "zenodo_record_id" may be the literal string
            "null" to mean a general alias.

    Raises:
        GazetteerAliasIngestError: if the row is missing required fields,
            references a location that isn't in the Gazetteer, or fails
            model-level validation (e.g. duplicate alias).
    """
    location_name = _get_alias_field(row, "location")
    alias_name = _get_alias_field(row, "alias")
    zenodo_record_id = _parse_zenodo_record_id(row.get("zenodo_record_id"))

    try:
        location = Gazetteer.objects.get(location=location_name)
    except Gazetteer.DoesNotExist as exc:
        raise GazetteerAliasIngestError(
            f"Alias '{alias_name}' references unknown gazetteer location "
            f"'{location_name}'. Ingest the gazetteer file first."
        ) from exc

    dataset = None
    if zenodo_record_id is not None:
        # datasets.Dataset is currently a minimal placeholder model - this
        # get_or_create is a temporary stand-in until real dataset ingestion
        # exists. Revisit once the datasets app is built out: a dataset
        # referenced by an alias should really already exist from a
        # published dataset upload, not be silently created here.
        from datasets.models import Dataset

        dataset, _ = Dataset.objects.get_or_create(zenodo_record_id=zenodo_record_id)

    alias, _ = GazetteerAlias.objects.update_or_create(
        dataset=dataset,
        alias=alias_name,
        defaults={"location": location},
    )


def ingest_gazetteer_aliases_csv(csv_file: TextIOBase) -> None:
    """Adds or edits GazetteerAlias rows from a parsed CSV file.

    Args:
        csv_file: A file-like object (text mode) containing the alias CSV,
            with columns "zenodo_record_id", "location", "alias".

    Raises:
        GazetteerAliasIngestError: if the file has no rows, or any row
            fails ingestion.
    """
    reader = csv.DictReader(csv_file)

    expected_columns = {"zenodo_record_id", "location", "alias"}
    if reader.fieldnames is None or not expected_columns.issubset(reader.fieldnames):
        raise GazetteerAliasIngestError(
            f"CSV must have columns {expected_columns}, got {reader.fieldnames}."
        )

    row_count = 0
    for row in reader:
        ingest_gazetteer_alias_row(row)
        row_count += 1

    if row_count == 0:
        raise GazetteerAliasIngestError("CSV file contains no data rows.")


def _get_alias_field(row: dict[str, str], field: str) -> str:
    value = row.get(field)

    if not value or value.strip().lower() == "null":
        raise GazetteerAliasIngestError(f"Row is missing a value for '{field}'.")

    return value.strip()


def _parse_zenodo_record_id(raw_value: str | None) -> int | None:
    if raw_value is None or raw_value.strip().lower() == "null":
        return None

    try:
        return int(raw_value)
    except ValueError as exc:
        raise GazetteerAliasIngestError(
            f"Invalid zenodo_record_id: {raw_value!r} is not an integer or 'null'."
        ) from exc