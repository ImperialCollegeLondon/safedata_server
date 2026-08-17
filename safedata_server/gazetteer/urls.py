"""Gazetteer app URLs."""

from django.urls import path

from gazetteer.views import (
    GazetteerAliasUploadView,
    GazetteerUploadView,
    gazetteer_aliases_download,
    gazetteer_aliases_hash,
    gazetteer_download,
    gazetteer_hash,
    gazetteer_map,
)

app_name = "gazetteer"

urlpatterns = [
    path("download/", gazetteer_download, name="download"),
    path("hash/", gazetteer_hash, name="hash"),
    path("upload/", GazetteerUploadView.as_view(), name="upload"),
    path("aliases/download/", gazetteer_aliases_download, name="alias-download"),
    path("aliases/hash/", gazetteer_aliases_hash, name="alias-hash"),
    path("aliases/upload/", GazetteerAliasUploadView.as_view(), name="alias-upload"),
    path("map/", gazetteer_map, name="map"),
]