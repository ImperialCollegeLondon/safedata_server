import json

from .models import Dataset, DatasetAuthors, DatasetKeywords


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
 