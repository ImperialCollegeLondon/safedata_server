"""Ingestion logic for populating the dataset table from a safedata_validator JSON export."""

import json
from datetime import date
from pathlib import Path
from typing import Any, cast

from django.conf import settings
from django.contrib.gis.geos import GEOSGeometry
from django.db import transaction

from gazetteer.models import Gazetteer, GazetteerAlias

from .models import (
    Dataset,
    DatasetAuthors,
    DatasetFields,
    DatasetFiles,
    DatasetFunders,
    DatasetKeywords,
    DatasetPermits,
    DatasetProject,
    DatasetWorksheets,
    Locations,
    Taxa,
)


class DatasetIngestError(Exception):
    """Raised when a dataset JSON export is malformed or fails validation."""



def _require(data: dict[str, Any], key: str, *, context: str) -> Any:
    value = data.get(key)
    if value is None:
        raise DatasetIngestError(f"Missing required field '{key}' in {context}.")
    return value


def _parse_date(value: str | None) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise DatasetIngestError(f"Invalid date value {value!r}: {exc}") from exc


def _stringify(value: Any) -> str | None:
    """Convert a non-string value to a JSON string for storage in a
    TextField. In case a non-string value is provided for a string
    field.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value)


def _dataset_fields_from_json(data: dict[str, Any]) -> dict[str, Any]:
    """Build the dict of Dataset scalar field values from a parsed export -
    shared between creating a new Dataset and updating an existing one."""
    temporal_extent = data.get("temporal_extent") or [None, None]
    latitudinal_extent = data.get("latitudinal_extent") or [None, None]
    longitudinal_extent = data.get("longitudinal_extent") or [None, None]

    return {
        "zenodo_record_id": _require(data, "zenodo_record_id", context="dataset"),
        "zenodo_concept_id": _require(data, "zenodo_concept_id", context="dataset"),
        "zenodo_publication_date": _parse_date(
            _require(data, "zenodo_publication_date", context="dataset")
        ),
        "title": _require(data, "title", context="dataset"),
        "description": data.get("description") or "",
        "access": _require(data, "access", context="dataset"),
        "embargo_date": _parse_date(data.get("embargo_date")),
        "access_conditions": data.get("access_conditions"),
        "validator_version": data.get("validator_version") or "",
        "gbif_timestamp": _parse_date(data.get("gbif_timestamp")),
        "temporal_extent_start": _parse_date(temporal_extent[0]),
        "temporal_extent_end": _parse_date(temporal_extent[1]),
        "latitudinal_extent_min": latitudinal_extent[0],
        "latitudinal_extent_max": latitudinal_extent[1],
        "longitudinal_extent_min": longitudinal_extent[0],
        "longitudinal_extent_max": longitudinal_extent[1],
    }


def _create_dataset(data: dict[str, Any]) -> Dataset:
    return Dataset.objects.create(**_dataset_fields_from_json(data))


def _update_dataset(dataset: Dataset, data: dict[str, Any]) -> Dataset:
    for field, value in _dataset_fields_from_json(data).items():
        setattr(dataset, field, value)
    dataset.save()
    return dataset


def _clear_dataset_children(dataset: Dataset) -> None:
    """Delete a dataset's child records before rebuilding from fresh ingestion.

    Deliberately does not touch GazetteerAlias, because that table is not
    owned by dataset ingestion and must survive a dataset being
    corrected/re-ingested.
    """
    DatasetProject.objects.filter(dataset=dataset).delete()
    DatasetAuthors.objects.filter(dataset=dataset).delete()
    DatasetFunders.objects.filter(dataset=dataset).delete()
    DatasetPermits.objects.filter(dataset=dataset).delete()
    DatasetKeywords.objects.filter(dataset=dataset).delete()
    DatasetWorksheets.objects.filter(dataset=dataset).delete()  # cascades to DatasetFields
    Taxa.objects.filter(dataset=dataset).delete()
    Locations.objects.filter(dataset=dataset).delete()
    dataset.files.all().delete()


def _ingest_worksheets(dataset: Dataset, worksheets_data: list[dict[str, Any]]) -> None:
    for worksheet_data in worksheets_data:
        worksheet = DatasetWorksheets.objects.create(
            dataset=dataset,
            name=_require(worksheet_data, "name", context="worksheet"),
            title=worksheet_data.get("title"),
            description=worksheet_data.get("description"),
            max_row=_require(worksheet_data, "max_row", context="worksheet"),
            max_col=_require(worksheet_data, "max_col", context="worksheet"),
            field_name_row=worksheet_data.get("field_name_row"),
            n_data_row=worksheet_data.get("n_data_row"),
            external=_stringify(worksheet_data.get("external")),
        )

        for field_data in worksheet_data.get("fields") or []:
            DatasetFields.objects.create(
                worksheet=worksheet,
                field_name=_require(field_data, "field_name", context="field"),
                description=field_data.get("description"),
                field_type=_require(field_data, "field_type", context="field"),
                units=field_data.get("units"),
                method=field_data.get("method"),
                levels=_stringify(field_data.get("levels")),
                range=_stringify(field_data.get("range")),
                taxon_field=field_data.get("taxon_field"),
                taxon_name=field_data.get("taxon_name"),
                interaction_field=field_data.get("interaction_field"),
                interaction_name=field_data.get("interaction_name"),
                col_idx=_require(field_data, "col_idx", context="field"),
            )


def _ingest_gbif_taxa(dataset: Dataset, gbif_taxa_data: list[dict[str, Any]]) -> None:
    for taxon_data in gbif_taxa_data:
        Taxa.objects.create(
            dataset=dataset,
            source=Taxa.SOURCE_GBIF,
            taxon_id=_require(taxon_data, "taxon_id", context="gbif_taxa"),
            parent_id=taxon_data.get("parent_id"),
            taxon_name=_require(taxon_data, "taxon_name", context="gbif_taxa"),
            taxon_rank=taxon_data.get("taxon_rank"),
            taxon_status=taxon_data.get("taxon_status"),
            worksheet_name=taxon_data.get("worksheet_name"),
        )


def _ingest_sequenced_taxa(
    dataset: Dataset, sequenced_taxa_data: dict[str, dict[str, Any]]
) -> None:
    # sequenced_taxa is a dict keyed by taxon-group name (e.g. "SeqTaxa"),
    # each holding its own taxon_index plus reference-database provenance
    # that applies to every taxon in that group.
    for group_data in sequenced_taxa_data.values():
        database_name = group_data.get("database_name")
        database_version = group_data.get("database_version")
        database_link = group_data.get("database_link")

        for taxon_data in group_data.get("taxon_index") or []:
            Taxa.objects.create(
                dataset=dataset,
                source=Taxa.SOURCE_SEQUENCE,
                taxon_id=_require(taxon_data, "taxon_id", context="sequenced_taxa"),
                parent_id=taxon_data.get("parent_id"),
                taxon_name=_require(taxon_data, "taxon_name", context="sequenced_taxa"),
                taxon_rank=taxon_data.get("taxon_rank"),
                taxon_status=taxon_data.get("taxon_status"),
                worksheet_name=taxon_data.get("worksheet_name"),
                database_name=database_name,
                database_version=database_version,
                database_link=database_link,
            )


def _ingest_locations(dataset: Dataset, locations_data: list[dict[str, Any]]) -> None:
    for location_data in locations_data:
        name = _require(location_data, "name", context="location")
        gazetteer_location = _resolve_gazetteer_location(dataset, name)

        wkt = location_data.get("wkt_wgs84")
        geometry = None
        local_geometry = None
        if wkt:
            try:
                geometry = GEOSGeometry(wkt, srid=4326)
                local_geometry = geometry.transform(settings.GAZETTEER_LOCAL_EPSG, clone=True)
            except Exception as exc:
                raise DatasetIngestError(
                    f"Location '{name}' has invalid wkt_wgs84: {exc}"
                ) from exc

        Locations.objects.create(
            dataset=dataset,
            name=name,
            new_location=bool(location_data.get("new_location", False)),
            gazetteer_location=gazetteer_location,
            geom_wgs84=geometry,
            geom_local=local_geometry,
        )


def _ingest_files(dataset: Dataset, data: dict[str, Any]) -> None:
    """Create the primary Excel file record for a dataset.

    Todo: update for examples with mutliple files when suitable examples come in.
    """
    filename = data.get("filename")
    if filename:
        DatasetFiles.objects.create(dataset=dataset, filename=filename)


def _resolve_gazetteer_location(dataset: Dataset, name: str) -> Gazetteer | None:
    """Resolve a dataset's location name against the global gazetteer.

    Checks for a direct match first, then a dataset-scoped alias, then a
    general alias - same resolution order established for the gazetteer
    alias table. Returns None if nothing matches (a genuinely new,
    unmatched location).
    """
    direct_match = Gazetteer.objects.filter(location=name).first()
    if direct_match is not None:
        return direct_match

    dataset_alias = GazetteerAlias.objects.filter(alias=name, dataset=dataset).first()
    if dataset_alias is not None:
        return cast(Gazetteer, dataset_alias.location)

    general_alias = GazetteerAlias.objects.filter(alias=name, dataset__isnull=True).first()
    if general_alias is not None:
        return cast(Gazetteer, general_alias.location)

    return None


def ingest_dataset(data: dict[str, Any]) -> Dataset:
    """Create (or replace) a Dataset and all its related records from one
    parsed safedata_validator JSON export.

    Every real export always has a populated zenodo_record_id, since a
    dataset only reaches safedata_server after being published to Zenodo.
    If that zenodo_record_id already exists in the database, the existing
    Dataset row is updated in place (same primary key) and its own child
    records (authors, worksheets, taxa, locations, etc.) are cleared and
    rebuilt from this export - treated as a correction to a
    previously-ingested dataset. Otherwise, a new Dataset row is created.

    Raises:
        DatasetIngestError: if required fields are missing or malformed.
    """
    with transaction.atomic():
        zenodo_record_id = _require(data, "zenodo_record_id", context="dataset")
        existing_dataset = Dataset.objects.filter(
            zenodo_record_id=zenodo_record_id
        ).first()

        if existing_dataset is not None:
            dataset = _update_dataset(existing_dataset, data)
            _clear_dataset_children(dataset)
        else:
            dataset = _create_dataset(data)

        for project_id in data.get("project_ids") or []:
            DatasetProject.objects.create(dataset=dataset, project_id=project_id)

        for author in data.get("authors") or []:
            DatasetAuthors.objects.create(
                dataset=dataset,
                name=_require(author, "name", context="author"),
                affiliation=author.get("affiliation"),
                email=author.get("email"),
                orcid=author.get("orcid"),
            )

        for funder in data.get("funders") or []:
            DatasetFunders.objects.create(
                dataset=dataset,
                body=_require(funder, "body", context="funder"),
                type=funder.get("type"),
                ref=funder.get("ref"),
                url=funder.get("url"),
            )

        for permit in data.get("permits") or []:
            DatasetPermits.objects.create(
                dataset=dataset,
                type=_require(permit, "type", context="permit"),
                authority=_require(permit, "authority", context="permit"),
                number=_require(permit, "number", context="permit"),
            )

        for keyword in data.get("keywords") or []:
            DatasetKeywords.objects.create(dataset=dataset, keyword=keyword)

        _ingest_worksheets(dataset, data.get("dataworksheets") or [])
        _ingest_gbif_taxa(dataset, data.get("gbif_taxa") or [])
        _ingest_sequenced_taxa(dataset, data.get("sequenced_taxa") or {})
        _ingest_locations(dataset, data.get("locations") or [])
        _ingest_files(dataset, data)

    return dataset