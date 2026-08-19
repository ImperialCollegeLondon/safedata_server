from django.db.models import Q
from django.shortcuts import get_object_or_404, render

from .models import Dataset


def dataset_list(request):
    """Searchable list of datasets. Shows only the latest version of each
    dataset by default (per zenodo_concept_id) - older versions remain
    reachable via the detail page of a search result, but aren't
    surfaced in the list itself.
    """
    query = request.GET.get("q", "").strip()

    datasets = Dataset.objects.latest_versions().order_by("-zenodo_publication_date")

    if query:
        datasets = datasets.filter(
            Q(title__icontains=query)
            | Q(description__icontains=query)
            | Q(keywords__keyword__icontains=query)
        ).distinct()

    context = {
        "datasets": datasets,
        "query": query,
    }
    return render(request, "datasets/list.html", context)


def dataset_detail(request, pk):
    """Full metadata for one dataset."""
    dataset = get_object_or_404(
        Dataset.objects.prefetch_related(
            "authors", "funders", "permits", "keywords", "worksheets__fields", "projects"
        ),
        pk=pk,
    )

    taxa_gbif_count = dataset.taxa.filter(source="gbif").count()
    taxa_sequence_count = dataset.taxa.filter(source="sequence").count()
    locations_resolved_count = dataset.locations.filter(
        gazetteer_location__isnull=False
    ).count()

    context = {
        "dataset": dataset,
        "taxa_gbif_count": taxa_gbif_count,
        "taxa_sequence_count": taxa_sequence_count,
        "locations_total_count": dataset.locations.count(),
        "locations_resolved_count": locations_resolved_count,
    }
    return render(request, "datasets/detail.html", context)