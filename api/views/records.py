"""Per-record metadata endpoint.

show_record(), show_worksheet(), get_taxa(), and get_locations() in the
legacy R package all operate on an already-fetched metadata object rather
than making their own separate API calls, so a single rich per-record
endpoint covers all of them client-side.

The response is a clean reconstruction from our normalized tables, not a
replica of the original safedata_validator export.
"""

from datasets.models import Dataset
from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView


def _serialize_record(dataset: Dataset) -> dict:
    return {
        "zenodo_record_id": dataset.zenodo_record_id,
        "zenodo_concept_id": dataset.zenodo_concept_id,
        "zenodo_publication_date": dataset.zenodo_publication_date,
        "title": dataset.title,
        "description": dataset.description,
        "filename": dataset.filename,
        "access": dataset.access,
        "embargo_date": dataset.embargo_date,
        "access_conditions": dataset.access_conditions,
        "validator_version": dataset.validator_version,
        "gbif_timestamp": dataset.gbif_timestamp,
        "temporal_extent": [
            dataset.temporal_extent_start,
            dataset.temporal_extent_end,
        ],
        "latitudinal_extent": [
            dataset.latitudinal_extent_min,
            dataset.latitudinal_extent_max,
        ],
        "longitudinal_extent": [
            dataset.longitudinal_extent_min,
            dataset.longitudinal_extent_max,
        ],
        "project_ids": [p.project_id for p in dataset.projects.all()],
        "authors": [
            {
                "name": a.name,
                "affiliation": a.affiliation,
                "email": a.email,
                "orcid": a.orcid,
            }
            for a in dataset.authors.all()
        ],
        "funders": [
            {"body": f.body, "type": f.type, "ref": f.ref, "url": f.url}
            for f in dataset.funders.all()
        ],
        "permits": [
            {"type": p.type, "authority": p.authority, "number": p.number}
            for p in dataset.permits.all()
        ],
        "keywords": [k.keyword for k in dataset.keywords.all()],
        "worksheets": [
            {
                "name": w.name,
                "title": w.title,
                "description": w.description,
                "max_row": w.max_row,
                "max_col": w.max_col,
                "field_name_row": w.field_name_row,
                "n_data_row": w.n_data_row,
                "fields": [
                    {
                        "field_name": f.field_name,
                        "description": f.description,
                        "field_type": f.field_type,
                        "units": f.units,
                        "method": f.method,
                        "levels": f.levels,
                        "range": f.range,
                        "taxon_field": f.taxon_field,
                        "taxon_name": f.taxon_name,
                        "interaction_field": f.interaction_field,
                        "interaction_name": f.interaction_name,
                        "col_idx": f.col_idx,
                    }
                    for f in w.fields.all()
                ],
            }
            for w in dataset.worksheets.all()
        ],
        "taxa": [
            {
                "source": t.source,
                "taxon_id": t.taxon_id,
                "parent_id": t.parent_id,
                "taxon_name": t.taxon_name,
                "taxon_rank": t.taxon_rank,
                "taxon_status": t.taxon_status,
                "worksheet_name": t.worksheet_name,
                "database_name": t.database_name,
                "database_version": t.database_version,
                "database_link": t.database_link,
            }
            for t in dataset.taxa.all()
        ],
        "locations": [
            {
                "name": loc.name,
                "new_location": loc.new_location,
                "gazetteer_location": (
                    loc.gazetteer_location.location if loc.gazetteer_location else None
                ),
                "wkt_wgs84": loc.geom_wgs84.wkt if loc.geom_wgs84 else None,
            }
            for loc in dataset.locations.all()
        ],
    }


class RecordMetadataView(APIView):
    """Full metadata for one dataset record, keyed by its Zenodo record id.

    GET /api/records/<zenodo_record_id>/
    """

    def get(self, request, zenodo_record_id, *args, **kwargs):
        dataset = get_object_or_404(
            Dataset.objects.prefetch_related(
                "projects",
                "authors",
                "funders",
                "permits",
                "keywords",
                "worksheets__fields",
                "taxa",
                "locations__gazetteer_location",
            ),
            zenodo_record_id=zenodo_record_id,
        )
        return Response(_serialize_record(dataset))