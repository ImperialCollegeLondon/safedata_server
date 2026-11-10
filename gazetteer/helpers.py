from django.core.serializers import serialize

from gazetteer.models import Gazetteer


def _current_gazetteer_geojson() -> str:
    """Serialize all Gazetteer rows to a GeoJSON FeatureCollection string."""
    return serialize(
        "geojson",
        Gazetteer.objects.all(),
        geometry_field="geom_wgs84",
        fields=("location",),
    )
