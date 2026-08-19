import hashlib
import json

from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render

from .models import Dataset, DatasetAuthors, DatasetKeywords


def dataset_list(request):
    """Searchable list of datasets. Shows only the latest version of each
    dataset by default (per zenodo_concept_id) - older versions remain
    reachable via the detail page of a search result, but aren't
    surfaced in the list itself.
    """
    query = request.GET.get("q", "").strip()

    datasets = Dataset.latest_versions().order_by("-zenodo_publication_date")

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


def _current_index_json() -> str:
    """Serialize a small subset of high-level metadata for each dataset's
    latest version to JSON. Regenerated from live DB state on every request,
    so it's always current.
    """
    datasets = (
        Dataset.latest_versions()
        .prefetch_related("authors", "keywords")
        .order_by("-zenodo_publication_date")
    )
 
    index = []
    for dataset in datasets:
        index.append(
            {
                "zenodo_record_id": dataset.zenodo_record_id,
                "zenodo_concept_id": dataset.zenodo_concept_id,
                "title": dataset.title,
                "authors": [
                    author.name
                    for author in DatasetAuthors.objects.filter(dataset=dataset)
                ],
                "keywords": [
                    kw.keyword for kw in DatasetKeywords.objects.filter(dataset=dataset)
                ],
                "access": dataset.access,
                "zenodo_publication_date": (
                    dataset.zenodo_publication_date.isoformat()
                    if dataset.zenodo_publication_date
                    else None
                ),
            }
        )
 
    return json.dumps(index, indent=2)
 
 
def dataset_index_download(request):
    """Serve the current dataset index as a downloadable JSON file."""
    content = _current_index_json()
 
    response = HttpResponse(content, content_type="application/json")
    response["Content-Disposition"] = 'attachment; filename="index.json"'
    return response
 
 
def dataset_index_hash(request):
    """Return the MD5 hash of the current dataset index."""
    content = _current_index_json()
    md5 = hashlib.md5(content.encode("utf-8")).hexdigest()
 
    return JsonResponse({"md5": md5})