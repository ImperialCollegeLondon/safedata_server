"""This module provides tests only routing to the resource files."""

from django.conf import settings
from django.urls import path
from django.views.static import serve


def serve_media_file(request, path):
    return serve(request, path, document_root=settings.MEDIA_ROOT)


urlpatterns = [
    path("resources/<path:path>", serve_media_file),
]
