"""API endpoints to deal with uploading dataset information."""

import json

from django.urls import reverse
from rest_framework.authentication import TokenAuthentication
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from datasets.helpers import _dataset_upload
from datasets.ingest import DatasetIngestError


class DatasetUploadView(APIView):
    """Authenticated upload of a safedata_validator dataset JSON export.

    Creates a new Dataset, or updates an existing one in place if its
    zenodo_record_id already exists (treated as a correction).
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
            dataset = _dataset_upload(uploaded_file)
        except (json.JSONDecodeError, DatasetIngestError) as exc:
            return Response({"detail": str(exc)}, status=400)

        return Response(
            {
                "dataset_id": dataset.id,  # Only really used in testing
                "url": reverse("datasets:detail", args=[dataset.zenodo_record_id]),
            },
            status=200,
        )
