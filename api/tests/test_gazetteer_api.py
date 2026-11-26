# gazetteer/tests.py
"""Tests for the gazetteer app: download/hash endpoints and authenticated
upload endpoints, for both the gazetteer and its aliases."""

import json
from hashlib import md5

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse

from gazetteer.models import Gazetteer, GazetteerAlias

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

UPDATED_GEOJSON = b"""{
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {"location": "Uploaded Site"},
            "geometry": {"type": "Point", "coordinates": [117.6, 4.7]}
        },
        {
            "type": "Feature",
            "properties": {"location": "New Uploaded Site"},
            "geometry": {"type": "Point", "coordinates": [117.6, 4.7]}
        }
    ]
}"""


MALFORMED_GEOJSON = b"""{"type": "Point", "coordinates": [117.6, 4.7]}"""

VALID_ALIAS_CSV = b'"zenodo_record_id","location","alias"\n"null","River Camp A","1"\n'

ALIAS_CSV_UNKNOWN_LOCATION = (
    b'"zenodo_record_id","location","alias"\n"null","Nonexistent Site","1"\n'
)


class TestGazetteerUpload:
    def test_requires_authentication(self, client, db):
        upload_file = SimpleUploadedFile(
            "gazetteer.geojson", VALID_GEOJSON, content_type="application/geo+json"
        )
        response = client.post(reverse("api:gazetteer-upload"), {"file": upload_file})

        assert response.status_code == 401
        assert Gazetteer.objects.count() == 0

    def test_succeeds_from_empty_with_valid_token(
        self, tmp_path, api_client_with_token, db
    ):
        """Tests that an empty Gazetteer model gets populated."""
        upload_file = SimpleUploadedFile(
            "gazetteer.geojson", VALID_GEOJSON, content_type="application/geo+json"
        )

        with override_settings(MEDIA_ROOT=tmp_path, DEBUG=True):
            response = api_client_with_token.post(
                reverse("api:gazetteer-upload"),
                {"file": upload_file},
                format="multipart",
            )

            assert response.status_code == 200
            assert response.json() == {"status": "ok"}

            # Check DB contains new data
            assert Gazetteer.objects.filter(location="Uploaded Site").exists()

            # Check resource files has been created and correctly hashed
            assert (tmp_path / "gazetteer.geojson").exists()
            assert (tmp_path / "hashes.json").exists()
            with open(tmp_path / "hashes.json") as hashfile:
                hashes = json.load(hashfile)
                assert md5(VALID_GEOJSON).hexdigest() == hashes["gazetteer.geojson"]

    def test_updates_with_valid_token(self, tmp_path, api_client_with_token, db):
        """Tests that a Gazetteer update gets populated correctly."""

        # Insert one of the named sites with differing coords
        Gazetteer.objects.create(
            location="Uploaded Site",
            geom_wgs84="POINT (0 0)",
            geom_local="POINT (0 0)",
        )
        assert not Gazetteer.objects.filter(location="New Uploaded Site").exists()

        upload_file = SimpleUploadedFile(
            "gazetteer.geojson", UPDATED_GEOJSON, content_type="application/geo+json"
        )

        with override_settings(MEDIA_ROOT=tmp_path, DEBUG=True):
            response = api_client_with_token.post(
                reverse("api:gazetteer-upload"),
                {"file": upload_file},
                format="multipart",
            )

            assert response.status_code == 200
            assert response.json() == {"status": "ok"}

            # Check DB contains new data and that coordinates have been updated on the
            # already existing  feature
            assert Gazetteer.objects.filter(location="New Uploaded Site").exists()
            updated_location = Gazetteer.objects.get(location="Uploaded Site")
            assert updated_location.geom_wgs84.coords == (117.6, 4.7)

            # Check resource files has been created and correctly hashed
            assert (tmp_path / "gazetteer.geojson").exists()
            assert (tmp_path / "hashes.json").exists()
            with open(tmp_path / "hashes.json") as hashfile:
                hashes = json.load(hashfile)
                assert md5(UPDATED_GEOJSON).hexdigest() == hashes["gazetteer.geojson"]

    def test_rejects_incomplete_gazeteer(self, sample_gazetteer, api_client_with_token):
        """Uses pre-populated sample_gazetteer fixture to trigger incomplete gazetteer
        error."""

        upload_file = SimpleUploadedFile(
            "gazetteer.geojson", VALID_GEOJSON, content_type="application/geo+json"
        )

        response = api_client_with_token.post(
            reverse("api:gazetteer-upload"),
            {"file": upload_file},
            format="multipart",
        )

        assert response.status_code == 400
        assert "detail" in response.json()
        assert (
            response.json()["detail"]
            == "Incomplete gazetteer uploaded - does not include all known features."
        )

    def test_rejects_malformed_geojson(self, api_client_with_token, db):
        upload_file = SimpleUploadedFile(
            "bad.geojson", MALFORMED_GEOJSON, content_type="application/geo+json"
        )
        response = api_client_with_token.post(
            reverse("api:gazetteer-upload"), {"file": upload_file}, format="multipart"
        )

        assert response.status_code == 400
        assert "detail" in response.json()

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
        response = client.post(
            reverse("api:gazetteer-alias-upload"), {"file": upload_file}
        )

        assert response.status_code == 401
        assert GazetteerAlias.objects.count() == 0

    def test_succeeds_with_valid_token(
        self, tmp_path, api_client_with_token, sample_gazetteer
    ):
        upload_file = SimpleUploadedFile(
            "aliases.csv", VALID_ALIAS_CSV, content_type="text/csv"
        )

        with override_settings(MEDIA_ROOT=tmp_path, DEBUG=True):
            response = api_client_with_token.post(
                reverse("api:gazetteer-alias-upload"),
                {"file": upload_file},
                format="multipart",
            )

            assert response.status_code == 200
            assert response.json() == {"status": "ok"}
            assert GazetteerAlias.objects.filter(alias="1").exists()

            # Check resource files has been created and correctly hashed
            assert (tmp_path / "location_aliases.csv").exists()
            assert (tmp_path / "hashes.json").exists()
            with open(tmp_path / "hashes.json") as hashfile:
                hashes = json.load(hashfile)
                assert (
                    md5(VALID_ALIAS_CSV).hexdigest() == hashes["location_aliases.csv"]
                )

    def test_rejects_unknown_gazetteer_location(
        self, api_client_with_token, sample_gazetteer
    ):
        upload_file = SimpleUploadedFile(
            "aliases.csv", ALIAS_CSV_UNKNOWN_LOCATION, content_type="text/csv"
        )
        response = api_client_with_token.post(
            reverse("api:gazetteer-alias-upload"),
            {"file": upload_file},
            format="multipart",
        )

        assert response.status_code == 400
        assert "detail" in response.json()
        assert GazetteerAlias.objects.count() == 0

    def test_requires_a_file(self, api_client_with_token, sample_gazetteer):
        response = api_client_with_token.post(
            reverse("api:gazetteer-alias-upload"), {}, format="multipart"
        )

        assert response.status_code == 400
