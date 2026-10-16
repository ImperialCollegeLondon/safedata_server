"""Ingestion logic for updating the Gazetteer from an uploaded GeoJSON file."""

import csv
import hashlib
import json
from io import TextIOBase
from typing import Any

from django.conf import settings
from django.contrib.gis.geos import GEOSGeometry
from django.core.files.storage import FileSystemStorage
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
        raise GazetteerIngestError("Feature is missing a 'location' property.")

    return location_name


def _get_geometry(feature: dict[str, Any], location_name: str) -> GEOSGeometry:
    geometry_data = feature.get("geometry")

    if not geometry_data:
        raise GazetteerIngestError(f"Feature '{location_name}' has no geometry.")

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
        # This alias is for a specific dataset only (not global). We should only
        # include this alias if the corresponding dataset already exists.
        from datasets.models import Dataset

        try:
            dataset = Dataset.objects.get(zenodo_record_id=zenodo_record_id)
        except Dataset.DoesNotExist as exc:
            raise GazetteerAliasIngestError(
                f"Alias '{alias_name}' references unknown dataset "
                f"(zenodo_record_id={zenodo_record_id}). Ingest that dataset first."
            ) from exc

    _ = GazetteerAlias.objects.update_or_create(
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

    with transaction.atomic():
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
    if raw_value is None or raw_value.strip().lower() in ["null", "na"]:
        return None

    try:
        return int(raw_value)
    except ValueError as exc:
        raise GazetteerAliasIngestError(
            f"Invalid zenodo_record_id: {raw_value!r} is not an integer, 'null' or 'na'."
        ) from exc


def update_gazetteer(file: Any) -> None:
    """Updates the gazetteer data from an uploaded file.

    The function takes the incoming file data and:
    1. checks it can be parsed as a GeoJSON FeatureCollection,
    2. checks that the data can be used to update Gazetteer,
    3. updates the rows of the Gazetteer model, and
    4. saves the original input file to the local resources directory.

    Args:
        geojson: A parsed GeoJSON FeatureCollection.

    Raises:
        GazetteerIngestError: if the file is not a valid FeatureCollection,
            or any feature fails ingestion.
    """

    # Allow json.JSONDecodeErrors to fall back to calling function
    geojson = json.load(file)

    if geojson.get("type") != "FeatureCollection":
        raise GazetteerIngestError(
            "Expected a GeoJSON FeatureCollection, got "
            f"{geojson.get('type', 'unknown')!r}."
        )

    features = geojson.get("features", [])
    if not features:
        raise GazetteerIngestError("FeatureCollection contains no features.")

    # Process the incoming data into a dictionary, keyed by location name, of update
    # dictionaries for the Gazetteer model
    incoming_data = dict([_process_feature(ft) for ft in features])
    known_names = Gazetteer.objects.all().values_list("location", flat=True)

    if not set(incoming_data.keys()).issuperset(known_names):
        raise GazetteerIngestError(
            "Incomplete gazetteer uploaded - does not include all known features."
        )

    # Wrap this in a transaction so that if the update fails, the data rolls back
    # and the user can fix that entry in their json file and re-upload the whole file.
    #
    # NOTE: Tried to do this with bulk create on pre-prepared Gazetteer objects but it
    #       cause 500 errors - couldn't see why. The code to do this is still here,
    #       commented out, in case we can fix it.
    #
    with transaction.atomic():
        # Gazetteer.objects.bulk_create(
        #     incoming_data.values(),
        #     update_conflicts=True,
        #     update_fields=["geom_local", "geom_wgs84"],
        # )
        for ft in incoming_data.values():
            Gazetteer.objects.update_or_create(**ft)

        # Update the resource files
        contents = file.read()
        FileSystemStorage().open("gazetteer.geojson", "wb").write(contents)

        with FileSystemStorage().open("hashes.json", "r") as hashfile:
            hashdata = json.load(hashfile)
            hashdata["gazetteer"] = hashlib.md5(contents).hexdigest()

        with FileSystemStorage().open("hashes.json", "w") as hashfile:
            json.dump(hashdata, hashfile)


# def _process_feature(feature: dict[str, Any]) -> tuple[str, Gazetteer]:
def _process_feature(feature: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Run validation and processing on a GeoJSON feature.

    Returns a tuple containing the location name and a Gazetteer object for insertion.
    """

    properties = feature.get("properties") or {}
    location_name = properties.get("location")

    if not location_name:
        raise GazetteerIngestError("Feature is missing a 'location' property.")

    geometry_data = feature.get("geometry")

    if not geometry_data:
        raise GazetteerIngestError(f"Feature '{location_name}' has no geometry.")

    try:
        # GeoJSON is always WGS84 by spec (RFC 7946), so this is always
        # SRID 4326 regardless of what the file's CRS member (if any) claims.
        geometry = GEOSGeometry(str(geometry_data).replace("'", '"'), srid=4326)
    except Exception as exc:
        raise GazetteerIngestError(
            f"Feature '{location_name}' has invalid geometry: {exc}"
        ) from exc

    # Get the geometry in the local projection
    local_geometry = geometry.transform(settings.GAZETTEER_LOCAL_EPSG, clone=True)

    # return location_name, Gazetteer(
    #     location=location_name,
    #     geom_wgs84=geometry,
    #     geom_local=local_geometry,
    # )

    return location_name, {
        "location": location_name,
        "geom_wgs84": geometry,
        "geom_local": local_geometry,
    }
