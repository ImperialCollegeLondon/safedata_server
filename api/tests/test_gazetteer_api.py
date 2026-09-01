# gazetteer/tests.py
"""Tests for the gazetteer app: download/hash endpoints and authenticated
upload endpoints, for both the gazetteer and its aliases."""

import hashlib

import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from gazetteer.models import Gazetteer, GazetteerAlias

# --- Shared fixtures ---------------------------------------------------------

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


@pytest.fixture
def sample_aliases(db, sample_gazetteer):
    camp_a = Gazetteer.objects.get(location="River Camp A")
    GazetteerAlias.objects.create(location=camp_a, alias="Camp A Alt Name")
    GazetteerAlias.objects.create(location=camp_a, alias="1")


@pytest.fixture
def api_client_with_token(db):
    user = User.objects.create_user(username="uploader", password="testpass123")
    token = Token.objects.create(user=user)

    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return client


# --- Sample upload payloads --------------------------------------------------

VALID_GEOJSON = b"""{
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {"location": "Uploaded Site"},
            "geometry": {"type": "Point", "coordinates": [117.6, 4.7]}
        }
    ]
}"""

MALFORMED_GEOJSON = b"""{"type": "Point", "coordinates": [117.6, 4.7]}"""

VALID_ALIAS_CSV = (
    b'"zenodo_record_id","location","alias"\n'
    b'"null","River Camp A","1"\n'
)

ALIAS_CSV_UNKNOWN_LOCATION = (
    b'"zenodo_record_id","location","alias"\n'
    b'"null","Nonexistent Site","1"\n'
)


class TestGazetteerDownload:
    def test_returns_geojson_feature_collection(self, client, sample_gazetteer):
        response = client.get(reverse("api:gazetteer-download"))

        assert response.status_code == 200
        assert response["Content-Type"] == "application/geo+json"
        assert 'attachment; filename="gazetteer.geojson"' in response["Content-Disposition"]

        content = response.json()
        assert content["type"] == "FeatureCollection"
        assert len(content["features"]) == 2

        locations = {f["properties"]["location"] for f in content["features"]}
        assert locations == {"River Camp A", "River Camp B"}

    def test_excludes_local_geometry(self, client, sample_gazetteer):
        response = client.get(reverse("api:gazetteer-download"))
        content = response.json()

        for feature in content["features"]:
            assert "geom_local" not in feature["properties"]


class TestGazetteerHash:
    def test_returns_md5(self, client, sample_gazetteer):
        response = client.get(reverse("api:gazetteer-hash"))

        assert response.status_code == 200
        data = response.json()
        assert "md5" in data
        assert len(data["md5"]) == 32

    def test_matches_downloaded_content(self, client, sample_gazetteer):
        download_response = client.get(reverse("api:gazetteer-download"))
        hash_response = client.get(reverse("api:gazetteer-hash"))

        expected_md5 = hashlib.md5(download_response.content).hexdigest()
        actual_md5 = hash_response.json()["md5"]

        assert actual_md5 == expected_md5

    def test_changes_when_gazetteer_changes(self, client, sample_gazetteer):
        initial_hash = client.get(reverse("api:gazetteer-hash")).json()["md5"]

        Gazetteer.objects.create(
            location="New Site",
            geom_wgs84="POINT (117.6000 4.7000)",
            geom_local="POINT (566000.00 520000.00)",
        )

        updated_hash = client.get(reverse("api:gazetteer-hash")).json()["md5"]

        assert updated_hash != initial_hash


class TestAliasDownload:
    def test_returns_csv(self, client, sample_aliases):
        response = client.get(reverse("api:gazetteer-alias-download"))

        assert response.status_code == 200
        assert response["Content-Type"] == "text/csv"
        assert 'attachment; filename="location_aliases.csv"' in response["Content-Disposition"]

        content = response.content.decode("utf-8")
        assert "zenodo_record_id" in content
        assert "location" in content
        assert "alias" in content
        assert "Camp A Alt Name" in content

    def test_uses_null_for_general_aliases(self, client, sample_aliases):
        response = client.get(reverse("api:gazetteer-alias-download"))
        content = response.content.decode("utf-8")

        # All fixture aliases are general (no dataset), so every data row
        # should have "null" in the zenodo_record_id column - matching the
        # convention in the existing production CSV file.
        lines = content.strip().splitlines()
        data_rows = lines[1:]  # skip header
        assert len(data_rows) == 2
        for row in data_rows:
            assert "null" in row


class TestAliasHash:
    def test_returns_md5(self, client, sample_aliases):
        response = client.get(reverse("api:gazetteer-alias-hash"))

        assert response.status_code == 200
        data = response.json()
        assert "md5" in data
        assert len(data["md5"]) == 32

    def test_matches_downloaded_content(self, client, sample_aliases):
        download_response = client.get(reverse("api:gazetteer-alias-download"))
        hash_response = client.get(reverse("api:gazetteer-alias-hash"))

        expected_md5 = hashlib.md5(download_response.content).hexdigest()
        actual_md5 = hash_response.json()["md5"]

        assert actual_md5 == expected_md5

    def test_changes_when_aliases_change(self, client, sample_aliases):
        initial_hash = client.get(reverse("api:gazetteer-alias-hash")).json()["md5"]

        camp_b = Gazetteer.objects.get(location="River Camp B")
        GazetteerAlias.objects.create(location=camp_b, alias="Camp B Alt Name")

        updated_hash = client.get(reverse("api:gazetteer-alias-hash")).json()["md5"]

        assert updated_hash != initial_hash


class TestGazetteerUpload:
    def test_requires_authentication(self, client, db):
        upload_file = SimpleUploadedFile(
            "gazetteer.geojson", VALID_GEOJSON, content_type="application/geo+json"
        )
        response = client.post(reverse("api:gazetteer-upload"), {"file": upload_file})

        assert response.status_code == 401
        assert Gazetteer.objects.count() == 0

    def test_succeeds_with_valid_token(self, api_client_with_token, db):
        upload_file = SimpleUploadedFile(
            "gazetteer.geojson", VALID_GEOJSON, content_type="application/geo+json"
        )
        response = api_client_with_token.post(
            reverse("api:gazetteer-upload"), {"file": upload_file}, format="multipart"
        )

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        assert Gazetteer.objects.filter(location="Uploaded Site").exists()

    def test_rejects_malformed_geojson(self, api_client_with_token, db):
        upload_file = SimpleUploadedFile(
            "bad.geojson", MALFORMED_GEOJSON, content_type="application/geo+json"
        )
        response = api_client_with_token.post(
            reverse("api:gazetteer-upload"), {"file": upload_file}, format="multipart"
        )

        assert response.status_code == 400
        assert "error" in response.json()

    def test_requires_a_file(self, api_client_with_token, db):
        response = api_client_with_token.post(
            reverse("api:gazetteer-upload"), {}, format="multipart"
        )

        assert response.status_code == 400


class TestAliasUpload:
    def test_requires_authentication(self, client, sample_gazetteer):
        upload_file = SimpleUploadedFile(
            "aliases.csv", VALID_ALIAS_CSV, content_type="text/csv"
        )
        response = client.post(reverse("api:gazetteer-alias-upload"), {"file": upload_file})

        assert response.status_code == 401
        assert GazetteerAlias.objects.count() == 0

    def test_succeeds_with_valid_token(self, api_client_with_token, sample_gazetteer):
        upload_file = SimpleUploadedFile(
            "aliases.csv", VALID_ALIAS_CSV, content_type="text/csv"
        )
        response = api_client_with_token.post(
            reverse("api:gazetteer-alias-upload"), {"file": upload_file}, format="multipart"
        )

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        assert GazetteerAlias.objects.filter(alias="1").exists()

    def test_rejects_unknown_gazetteer_location(self, api_client_with_token, sample_gazetteer):
        upload_file = SimpleUploadedFile(
            "aliases.csv", ALIAS_CSV_UNKNOWN_LOCATION, content_type="text/csv"
        )
        response = api_client_with_token.post(
            reverse("api:gazetteer-alias-upload"), {"file": upload_file}, format="multipart"
        )

        assert response.status_code == 400
        assert "error" in response.json()
        assert GazetteerAlias.objects.count() == 0

    def test_requires_a_file(self, api_client_with_token, sample_gazetteer):
        response = api_client_with_token.post(
            reverse("api:gazetteer-alias-upload"), {}, format="multipart"
        )

        assert response.status_code == 400