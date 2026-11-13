# gazetteer/tests.py
"""Tests for the gazetteer app: download/hash endpoints and authenticated
upload endpoints, for both the gazetteer and its aliases."""

from django.core.files.uploadedfile import SimpleUploadedFile
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

    def test_succeeds_with_valid_token(self, api_client_with_token, sample_gazetteer):
        upload_file = SimpleUploadedFile(
            "aliases.csv", VALID_ALIAS_CSV, content_type="text/csv"
        )
        response = api_client_with_token.post(
            reverse("api:gazetteer-alias-upload"),
            {"file": upload_file},
            format="multipart",
        )

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        assert GazetteerAlias.objects.filter(alias="1").exists()

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
