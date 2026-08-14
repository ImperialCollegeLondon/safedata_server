"""Gazetteer views."""

import hashlib

from django.core.serializers import serialize
from django.http import HttpResponse, JsonResponse
from gazetteer.models import Gazetteer


def _current_gazetteer_geojson() -> str:
    """Serialize all Gazetteer rows to a GeoJSON FeatureCollection string."""
    return serialize(
        "geojson",
        Gazetteer.objects.all(),
        geometry_field="geom_wgs84",
        fields=("location",),
    )


def gazetteer_download(request):
    """Serve the current gazetteer as a downloadable GeoJSON file."""
    content = _current_gazetteer_geojson()

    response = HttpResponse(content, content_type="application/geo+json")
    response["Content-Disposition"] = 'attachment; filename="gazetteer.geojson"'
    return response


def gazetteer_hash(request):
    """Return the MD5 hash of the current gazetteer file.

    Downstream tools (e.g. the safedata R package) use this to check
    whether their local copy is stale, without downloading the full file.
    """
    content = _current_gazetteer_geojson()
    md5 = hashlib.md5(content.encode("utf-8")).hexdigest()

    return JsonResponse({"md5": md5})
