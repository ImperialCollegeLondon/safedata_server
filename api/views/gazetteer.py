import json

from rest_framework.authentication import TokenAuthentication
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from gazetteer.ingest import (
    GazetteerAliasIngestError,
    GazetteerIngestError,
    update_gazetteer,
    update_gazetteer_aliases,
)


class GazetteerUploadView(APIView):
    """Authenticated upload of a new gazetteer GeoJSON file.

    Adds / edits Gazetteer rows by location name.
    """

    authentication_classes = (TokenAuthentication,)
    permission_classes = (IsAuthenticated,)
    parser_classes = (MultiPartParser,)

    def post(self, request, *args, **kwargs):
        uploaded_file = request.FILES.get("file")
        if uploaded_file is None:
            return Response(
                {"detail": "No file provided. Upload under the 'file' key."},
                status=400,
            )

        try:
            update_gazetteer(uploaded_file)
        except json.JSONDecodeError as exc:
            return Response({"detail": f"Invalid JSON: {exc}"}, status=400)
        except GazetteerIngestError as exc:
            return Response({"detail": str(exc)}, status=400)

        return Response({"status": "ok"}, status=200)


class GazetteerAliasUploadView(APIView):
    """Authenticated upload of a new gazetteer aliases CSV file.

    Adds/edits GazetteerAlias rows keyed on (dataset, alias). Referenced
    gazetteer locations must already exist - ingest the gazetteer file
    first if uploading both.
    """

    authentication_classes = (TokenAuthentication,)
    permission_classes = (IsAuthenticated,)
    parser_classes = (MultiPartParser,)

    def post(self, request, *args, **kwargs):
        uploaded_file = request.FILES.get("file")
        if uploaded_file is None:
            return Response(
                {"detail": "No file provided. Upload under the 'file' key."},
                status=400,
            )

        try:
            update_gazetteer_aliases(uploaded_file.file)
        except (UnicodeEncodeError, GazetteerAliasIngestError) as exc:
            return Response({"detail": str(exc)}, status=400)

        return Response({"status": "ok"}, status=200)
