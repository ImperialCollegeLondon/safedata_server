from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from datasets.models import Dataset, Taxa


def _serialize_gbif_coverage(queryset) -> dict:
    """Merge GBIF taxa with globally-comparable taxon_id. Entries 
    with taxon_id == -1 (user-defined) have no identity to merge
    on, so each is kept as its own entry, identifiable only by name,
    hanging off its real parent_id.
    """
    grouped: dict[int, dict] = {}
    unmatched: list[dict] = []

    for taxon in queryset.select_related("dataset"):
        if taxon.taxon_id > 0:
            entry = grouped.setdefault(
                taxon.taxon_id,
                {
                    "taxon_id": taxon.taxon_id,
                    "parent_id": taxon.parent_id,
                    "taxon_name": taxon.taxon_name,
                    "taxon_rank": taxon.taxon_rank,
                    "zenodo_record_ids": set(),
                },
            )
            entry["zenodo_record_ids"].add(taxon.dataset.zenodo_record_id)
        else:
            unmatched.append(
                {
                    "taxon_id": taxon.taxon_id,
                    "parent_id": taxon.parent_id,
                    "taxon_name": taxon.taxon_name,
                    "taxon_rank": taxon.taxon_rank,
                    "worksheet_name": taxon.worksheet_name,
                    "zenodo_record_ids": [taxon.dataset.zenodo_record_id],
                }
            )

    entries = [
        {**entry, "zenodo_record_ids": sorted(entry["zenodo_record_ids"])}
        for entry in grouped.values()
    ] + unmatched

    return {"count": len(entries), "taxa": entries}


def _serialize_sequence_coverage(queryset) -> dict:
    """Group sequence-derived taxa by (taxon_rank, taxon_name), since
    their taxon_id/parent_id values are always local placeholders with
    no cross-dataset meaning at all - name/rank is the only usable
    identity for building a shared hierarchy across datasets.
    """
    grouped: dict[tuple[str | None, str], dict] = {}

    for taxon in queryset.select_related("dataset"):
        key = (taxon.taxon_rank, taxon.taxon_name)
        entry = grouped.setdefault(
            key,
            {
                "taxon_name": taxon.taxon_name,
                "taxon_rank": taxon.taxon_rank,
                "zenodo_record_ids": set(),
            },
        )
        entry["zenodo_record_ids"].add(taxon.dataset.zenodo_record_id)

    entries = [
        {**entry, "zenodo_record_ids": sorted(entry["zenodo_record_ids"])}
        for entry in grouped.values()
    ]

    return {"count": len(entries), "taxa": entries}


class GlobalGbifTaxonCoverageView(APIView):
    """The complete curated GBIF taxonomic tree across all datasets'
    latest versions.

    GET /api/taxon_coverage/gbif/
    """

    def get(self, request, *args, **kwargs):
        queryset = Taxa.objects.filter(
            source=Taxa.SOURCE_GBIF, dataset__in=Dataset.latest_versions()
        )
        return Response(_serialize_gbif_coverage(queryset))


class GlobalSequenceTaxonCoverageView(APIView):
    """The sequence-derived taxonomic hierarchy across all datasets'
    latest versions, grouped by rank/name since there's no stable id.

    GET /api/taxon_coverage/sequence/
    """

    def get(self, request, *args, **kwargs):
        queryset = Taxa.objects.filter(
            source=Taxa.SOURCE_SEQUENCE, dataset__in=Dataset.latest_versions()
        )
        return Response(_serialize_sequence_coverage(queryset))


class RecordTaxaView(APIView):
    """The taxon set for one specific dataset record - auto-detects
    whether it's GBIF or sequence-derived taxa, since a dataset only
    ever has one or the other, never both.

    GET /api/records/<zenodo_record_id>/taxa/
    """

    def get(self, request, zenodo_record_id, *args, **kwargs):
        dataset = get_object_or_404(Dataset, zenodo_record_id=zenodo_record_id)
        queryset = dataset.taxa.all()

        if not queryset.exists():
            return Response({"count": 0, "taxa": [], "source": None})

        # A dataset only ever has one taxa source, never both - trust
        # that and key off whichever the first row happens to be.
        source = queryset.first().source

        if source == Taxa.SOURCE_GBIF:
            result = _serialize_gbif_coverage(queryset)
        else:
            result = _serialize_sequence_coverage(queryset)

        result["source"] = source
        return Response(result)