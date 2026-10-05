import csv
import io

from django.core.serializers import serialize

from gazetteer.models import Gazetteer, GazetteerAlias


def _current_gazetteer_geojson() -> str:
    """Serialize all Gazetteer rows to a GeoJSON FeatureCollection string."""
    return serialize(
        "geojson",
        Gazetteer.objects.all(),
        geometry_field="geom_wgs84",
        fields=("location",),
    )

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
