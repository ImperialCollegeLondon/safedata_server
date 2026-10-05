"""API endpoints to deal with downloading and uploading dataset information."""

import hashlib
import json

from django.http import HttpResponse, JsonResponse
from rest_framework.authentication import TokenAuthentication
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from datasets.helpers import _current_index_json
from datasets.ingest import DatasetIngestError, ingest_dataset


def dataset_index_download(request):
    """Serve the current dataset index as a downloadable JSON file."""
    content = _current_index_json()
 
    response = HttpResponse(content, content_type="application/json")
    response["Content-Disposition"] = 'attachment; filename="index.json"'
    return response
 
 
def dataset_index_hash(request):
    """Return the MD5 hash of the current dataset index."""
    content = _current_index_json()
    md5 = hashlib.md5(content.encode("utf-8")).hexdigest()
 
    return JsonResponse({"md5": md5})


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
                {"error": "No file provided. Upload under the 'file' key."},
                status=400,
            )
 
        try:
            data = json.load(uploaded_file)
        except json.JSONDecodeError as exc:
            return Response({"error": f"Invalid JSON: {exc}"}, status=400)
 
        try:
            dataset = ingest_dataset(data)
        except DatasetIngestError as exc:
            return Response({"error": str(exc)}, status=400)
 
        return Response({"status": "ok", "dataset_id": dataset.id}, status=200)