from collections import defaultdict

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
    """Group sequence-derived taxa into a global hierarchy using their
    full ancestor name path resolved per-dataset since taxon_id/parent_id 
    are only locally meaningful.
    Identically named paths across different datasets are merged into one
    node; synthetic taxon_id/parent_id values are assigned so the
    response has the same shape as the GBIF coverage endpoint, letting
    the same tree-building logic work for both.
    """
    by_dataset = defaultdict(list)
    for taxon in queryset.select_related("dataset"):
        by_dataset[taxon.dataset_id].append(taxon)

    # path (tuple of (rank, name) pairs, root to leaf) -> merged node data
    nodes_by_path: dict[tuple, dict] = {}

    for taxa_list in by_dataset.values():
        local_by_id = {t.taxon_id: t for t in taxa_list}
        record_id = taxa_list[0].dataset.zenodo_record_id
        path_cache: dict[int, tuple] = {}

        def resolve_path(taxon):
            if taxon.taxon_id in path_cache:
                return path_cache[taxon.taxon_id]
            if taxon.parent_id is None or taxon.parent_id not in local_by_id:
                path = ((taxon.taxon_rank, taxon.taxon_name),)
            else:
                parent_path = resolve_path(local_by_id[taxon.parent_id])
                path = parent_path + ((taxon.taxon_rank, taxon.taxon_name),)
            path_cache[taxon.taxon_id] = path
            return path

        for taxon in taxa_list:
            path = resolve_path(taxon)
            node = nodes_by_path.setdefault(
                path,
                {
                    "taxon_name": taxon.taxon_name,
                    "taxon_rank": taxon.taxon_rank,
                    "parent_path": path[:-1] if len(path) > 1 else None,
                    "zenodo_record_ids": set(),
                },
            )
            node["zenodo_record_ids"].add(record_id)

    path_to_id = {path: i + 1 for i, path in enumerate(nodes_by_path)}

    entries = [
        {
            "taxon_id": path_to_id[path],
            "parent_id": path_to_id[node["parent_path"]] if node["parent_path"] else None,
            "taxon_name": node["taxon_name"],
            "taxon_rank": node["taxon_rank"],
            "zenodo_record_ids": sorted(node["zenodo_record_ids"]),
        }
        for path, node in nodes_by_path.items()
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