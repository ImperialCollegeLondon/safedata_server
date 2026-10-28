import hashlib
import json
from typing import Any

from django.core.files.storage import FileSystemStorage

from .ingest import ingest_dataset
from .models import Dataset, DatasetFiles


def _current_index_json() -> str:
    """Serialise file level information across all datasets to JSON.

    The content is repetitive, but is structured to minimise the client side processing
    in `safedata`.
    """

    index: list[dict] = []
    latest_version_ids = [
        v[0] for v in Dataset.latest_versions().values_list("zenodo_record_id")
    ]

    index = [
        {
            "publication_date": file.dataset.zenodo_publication_date.isoformat()
            if file.dataset.zenodo_publication_date
            else None,
            "zenodo_concept_id": file.dataset.zenodo_concept_id,
            "zenodo_record_id": file.dataset.zenodo_record_id,
            "dataset_access": file.dataset.access.lower(),
            "dataset_embargo": file.dataset.embargo_date.isoformat()
            if file.dataset.embargo_date
            else None,
            "dataset_title": file.dataset.title,
            "most_recent": file.dataset.zenodo_record_id in latest_version_ids,
            "checksum": file.checksum,
            "filename": file.filename,
            "filesize": file.filesize,
        }
        for file in DatasetFiles.objects.all()
    ]

    return json.dumps(index, indent=2)


def _dataset_upload(file: Any) -> Dataset:

    # Allow json.JSONDecodeErrors to fall back to calling function
    data = json.load(file)

    # Allow ingest_dataset to fall back with DatasetIngestError
    dataset = ingest_dataset(data)

    # Generate index after update
    index_bytes: bytes = _current_index_json().encode()

    # Update the resource files
    FileSystemStorage().open("index.json", "wb").write(index_bytes)

    with FileSystemStorage().open("hashes.json", "r") as hashfile:
        hashdata = json.load(hashfile)
        hashdata["index"] = hashlib.md5(index_bytes).hexdigest()

    with FileSystemStorage().open("hashes.json", "w") as hashfile:
        json.dump(hashdata, hashfile)

    return dataset
