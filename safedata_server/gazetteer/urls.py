"""Gazetteer app URLs."""

from django.urls import path

from gazetteer.views import (
    GazetteerAliasUploadView,
    GazetteerUploadView,
    gazetteer_download,
    gazetteer_hash,
)

app_name = "gazetteer"

urlpatterns = [
    path("download/", gazetteer_download, name="download"),
    path("hash/", gazetteer_hash, name="hash"),
    path("upload/", GazetteerUploadView.as_view(), name="upload"),
    path("aliases/upload/", GazetteerAliasUploadView.as_view(), name="alias-upload"),
]