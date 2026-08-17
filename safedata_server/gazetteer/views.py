"""Gazetteer views."""

import hashlib
import io
import json

from django.core.serializers import serialize
from django.http import HttpResponse, JsonResponse
from rest_framework.authentication import TokenAuthentication
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from gazetteer.models import Gazetteer

from .ingest import (
    GazetteerAliasIngestError,
    GazetteerIngestError,
    ingest_gazetteer_aliases_csv,
    ingest_multiple_gazetteer_entries,
)


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




class GazetteerUploadView(APIView):
    """Authenticated upload of a new gazetteer GeoJSON file.

    Upserts Gazetteer rows by location name. Never deletes existing rows,
    even if they're absent from the uploaded file.
    """

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser]

    def post(self, request, *args, **kwargs):
        uploaded_file = request.FILES.get("file")
        if uploaded_file is None:
            return Response(
                {"error": "No file provided. Upload under the 'file' key."},
                status=400,
            )

        try:
            geojson = json.load(uploaded_file)
        except json.JSONDecodeError as exc:
            return Response({"error": f"Invalid JSON: {exc}"}, status=400)

        try:
            ingest_multiple_gazetteer_entries(geojson)
        except GazetteerIngestError as exc:
            return Response({"error": str(exc)}, status=400)

        return Response({"status": "ok"}, status=200)


class GazetteerAliasUploadView(APIView):
    """Authenticated upload of a new gazetteer aliases CSV file.

    Upserts GazetteerAlias rows keyed on (dataset, alias). Referenced
    gazetteer locations must already exist - ingest the gazetteer file
    first if uploading both.
    """

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser]

    def post(self, request, *args, **kwargs):
        uploaded_file = request.FILES.get("file")
        if uploaded_file is None:
            return Response(
                {"error": "No file provided. Upload under the 'file' key."},
                status=400,
            )

        # csv.DictReader needs a text-mode file; uploaded files arrive as
        # bytes, so wrap and decode.
        text_file = io.TextIOWrapper(uploaded_file.file, encoding="utf-8")

        try:
            ingest_gazetteer_aliases_csv(text_file)
        except GazetteerAliasIngestError as exc:
            return Response({"error": str(exc)}, status=400)

        return Response({"status": "ok"}, status=200)