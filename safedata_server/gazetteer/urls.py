"""Gazetteer app URLs."""

from django.urls import path

from gazetteer.views import gazetteer_download, gazetteer_hash

app_name = "gazetteer"

urlpatterns = [
    path("download/", gazetteer_download, name="download"),
    path("hash/", gazetteer_hash, name="hash"),
]