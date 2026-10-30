"""Gazetteer views."""

import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .ingest import (
    GazetteerAliasIngestError,
    GazetteerIngestError,
    ingest_multiple_gazetteer_entries,
    update_gazetteer_aliases,
)


def gazetteer_map(request):
    """Render a Leaflet map of all current gazetteer locations."""
    return render(request, "gazetteer/map.html")


@login_required
def gazetteer_upload_page(request):
    """A simple browser-based upload page for the gazetteer GeoJSON and
    aliases CSV, alongside the existing token-authenticated API
    endpoints."""
    if request.method == "POST":
        upload_type = request.POST.get("upload_type")

        if upload_type == "gazetteer":
            _handle_gazetteer_upload(request)
        elif upload_type == "aliases":
            _handle_aliases_upload(request)

        return redirect("gazetteer:upload-page")

    return render(request, "gazetteer/upload.html")


def _handle_gazetteer_upload(request):
    uploaded_file = request.FILES.get("file")
    if uploaded_file is None:
        messages.error(request, "No gazetteer file was provided.")
        return

    try:
        data = json.load(uploaded_file)
        ingest_multiple_gazetteer_entries(data)
    except (json.JSONDecodeError, GazetteerIngestError) as exc:
        messages.error(request, f"Gazetteer upload failed: {exc}")
        return

    messages.success(request, "Gazetteer uploaded successfully.")


def _handle_aliases_upload(request):
    uploaded_file = request.FILES.get("file")

    # Look for missing file
    if uploaded_file is None:
        messages.error(request, "No aliases file was provided.")
        return

    try:
        update_gazetteer_aliases(uploaded_file.file)
    except (UnicodeDecodeError, GazetteerAliasIngestError) as exc:
        messages.error(request, f"Aliases upload failed: {exc}")
        return

    messages.success(request, "Aliases uploaded successfully.")
