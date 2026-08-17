# gazetteer/tests.py
"""Tests for the gazetteer download and hash endpoints."""

import hashlib

import pytest
from django.urls import reverse

from .models import Gazetteer


@pytest.fixture
def sample_gazetteer(db):
    Gazetteer.objects.create(
        location="River Camp A",
        geom_wgs84="POINT (117.6194 4.7461)",
        geom_local="POINT (568690.28 524629.41)",
    )
    Gazetteer.objects.create(
        location="River Camp B",
        geom_wgs84="POINT (117.6231 4.7502)",
        geom_local="POINT (569100.22 525083.00)",
    )


def test_download_returns_geojson_feature_collection(client, sample_gazetteer):
    response = client.get(reverse("gazetteer:download"))

    assert response.status_code == 200
    assert response["Content-Type"] == "application/geo+json"
    assert 'attachment; filename="gazetteer.geojson"' in response["Content-Disposition"]

    content = response.json()
    assert content["type"] == "FeatureCollection"
    assert len(content["features"]) == 2

    locations = {f["properties"]["location"] for f in content["features"]}
    assert locations == {"River Camp A", "River Camp B"}


def test_download_excludes_local_geometry(client, sample_gazetteer):
    response = client.get(reverse("gazetteer:download"))
    content = response.json()

    for feature in content["features"]:
        # Only geom_wgs84 should be present in the download - geom_local
        # is an internal detail, not meant for external consumers.
        assert "geom_local" not in feature["properties"]


def test_hash_endpoint_returns_md5(client, sample_gazetteer):
    response = client.get(reverse("gazetteer:hash"))

    assert response.status_code == 200
    data = response.json()
    assert "md5" in data
    assert len(data["md5"]) == 32  # a valid MD5 hex digest is always 32 chars


def test_hash_matches_downloaded_content(client, sample_gazetteer):
    """The whole point of the hash endpoint - it must reflect exactly what
    the download endpoint serves, or downstream tools comparing hashes
    will get false mismatches."""
    download_response = client.get(reverse("gazetteer:download"))
    hash_response = client.get(reverse("gazetteer:hash"))

    expected_md5 = hashlib.md5(download_response.content).hexdigest()
    actual_md5 = hash_response.json()["md5"]

    assert actual_md5 == expected_md5


def test_hash_changes_when_gazetteer_changes(client, sample_gazetteer):
    """Confirms the hash reflects live DB state, not a cached/stale value."""
    initial_hash = client.get(reverse("gazetteer:hash")).json()["md5"]

    Gazetteer.objects.create(
        location="New Site",
        geom_wgs84="POINT (117.6000 4.7000)",
        geom_local="POINT (566000.00 520000.00)",
    )

    updated_hash = client.get(reverse("gazetteer:hash")).json()["md5"]

    assert updated_hash != initial_hash