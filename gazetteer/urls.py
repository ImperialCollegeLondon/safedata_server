"""Gazetteer app URLs."""

from django.urls import path

from gazetteer.views import gazetteer_map

app_name = "gazetteer"

urlpatterns = [
    path("map/", gazetteer_map, name="map"),
]