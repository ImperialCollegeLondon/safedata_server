"""This test module tests the resource URLS.

This isn't strictly part of the API testing but these URLS sit alongside the API in day
to day use. The tests need to override the model settings to access the files provided
by the resources_directory fixture through the MEDIA_URL. This also requires that DEBUG
is explicitly set to True to provide file access through the development-only `static()`
rather than through the configured nginx pathway used in production.
"""

import json
from csv import DictReader
from hashlib import md5

import pytest
from django.test import override_settings


@pytest.fixture(autouse=True)
def resource_urlconf(settings):
    """Use test only url settings to access resources in this module."""
    settings.ROOT_URLCONF = "api.tests.urls"


def test_get_hashes(client, resources_directory):

    with override_settings(MEDIA_ROOT=resources_directory, DEBUG=True):
        response = client.get("/resources/hashes.json")

        assert response.status_code == 200
        assert response["Content-Type"] == "application/json"
        assert 'inline; filename="hashes.json"' in response["Content-Disposition"]

        content = json.loads(b"".join(response.streaming_content).decode("UTF-8"))
        assert content.keys() == {"gazetteer.geojson", "location_aliases.csv"}


def test_get_gazetteer(client, resources_directory):

    with override_settings(MEDIA_ROOT=resources_directory, DEBUG=True):
        response = client.get("/resources/gazetteer.geojson")

        # Got a file of the right type and name
        assert response.status_code == 200
        assert response["Content-Type"] == "application/octet-stream"
        assert 'inline; filename="gazetteer.geojson"' in response["Content-Disposition"]

        # Data contains expected payload
        data = b"".join(response.streaming_content)
        content = json.loads(data.decode("UTF-8"))
        assert content["type"] == "FeatureCollection"
        assert len(content["features"]) == 2

        locations = {f["properties"]["location"] for f in content["features"]}
        assert locations == {"River Camp A", "River Camp B"}

        # Data hash matches provided hash. This is a rather weak test that the
        # provisioned resource files are setup correctly and that the file is streamed
        # as expected.
        hashes_response = client.get("/resources/hashes.json")
        hashes = json.loads(b"".join(hashes_response.streaming_content).decode("UTF-8"))

        assert md5(data).hexdigest() == hashes["gazetteer.geojson"]


def test_get_location_aliases(client, resources_directory):

    with override_settings(MEDIA_ROOT=resources_directory, DEBUG=True):
        response = client.get("/resources/location_aliases.csv")

        # Got a file of the right type and name
        assert response.status_code == 200
        assert response["Content-Type"] == "text/csv"
        assert (
            'inline; filename="location_aliases.csv"' in response["Content-Disposition"]
        )

        # Data contains expected payload
        data = b"".join(response.streaming_content)
        content = DictReader(data.decode("UTF-8").split("\n"))

        rows = list(content)
        assert len(rows) == 2
        aliases = {r["alias"] for r in rows}
        assert aliases == {"Camp A Alt Name", "1"}

        # Data hash matches provided hash. This is a rather weak test that the
        # provisioned resource files are setup correctly and that the file is streamed
        # as expected.
        hashes_response = client.get("/resources/hashes.json")
        hashes = json.loads(b"".join(hashes_response.streaming_content).decode("UTF-8"))

        assert md5(data).hexdigest() == hashes["location_aliases.csv"]
