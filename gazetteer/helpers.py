import csv
import io

from gazetteer.models import GazetteerAlias


def _current_aliases_csv() -> str:
    """Serialize all GazetteerAlias rows to CSV, matching the upload format."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, quoting=csv.QUOTE_ALL)
    writer.writerow(["zenodo_record_id", "location", "alias"])

    for alias in GazetteerAlias.objects.select_related("location").order_by("id"):
        zenodo_record_id = getattr(alias.dataset, "zenodo_record_id", "null")
        location = getattr(alias.location, "location", "null")
        writer.writerow([zenodo_record_id, location, alias.alias])

    return buffer.getvalue()
