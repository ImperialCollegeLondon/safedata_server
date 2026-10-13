import json

from .models import Dataset


def _current_index_json() -> str:
    """Serialise file level information across all datasets to JSON.

    Might be a clever way to do this with django serializers but that includes model
    information and this is purely for export.
    """

    index: list[dict] = []

    for ds in Dataset.objects.all():
        ds_dict = {
            "publication_date": ds.zenodo_publication_date.isoformat()
            if ds.zenodo_publication_date
            else None,
            "zenodo_concept_id": ds.zenodo_concept_id,
            "zenodo_record_id": ds.zenodo_record_id,
            "dataset_access": ds.access.lower(),
            "dataset_embargo": ds.embargo_date.isoformat() if ds.embargo_date else None,
            "dataset_title": ds.title,
        }

        ds_dict["files"] = [
            {
                "checksum": f.checksum,
                "filename": f.filename,
                "filesize": f.filesize,
            }
            for f in ds.files.all()
        ]
        index.append(ds_dict)

    return json.dumps(index, indent=2)
