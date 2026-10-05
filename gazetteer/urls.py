"""Gazetteer app URLs."""

from django.urls import path

from gazetteer.views import gazetteer_map, gazetteer_upload_page

app_name = "gazetteer"

urlpatterns = [
    path("map/", gazetteer_map, name="map"),
    path("upload/", gazetteer_upload_page, name="upload-page"),
]