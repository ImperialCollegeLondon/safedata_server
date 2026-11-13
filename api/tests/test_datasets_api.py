import json

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse

from datasets.models import Dataset
from datasets.tests import base_dataset_json


class TestDatasetUpload:
    def _upload_file(self, data):
        content = json.dumps(data).encode("utf-8")
        return SimpleUploadedFile(
            "dataset.json", content, content_type="application/json"
        )

    def test_requires_authentication(self, client, db):
        upload_file = self._upload_file(base_dataset_json())
        response = client.post(reverse("api:datasets-upload"), {"file": upload_file})

        assert response.status_code == 401
        assert Dataset.objects.count() == 0

    def test_succeeds_with_valid_token_and_creates_dataset(
        self, tmp_path, api_client_with_token, db
    ):
        upload_file = self._upload_file(base_dataset_json(title="Uploaded via API"))

        with override_settings(MEDIA_ROOT=tmp_path, DEBUG=True):
            response = api_client_with_token.post(
                reverse("api:datasets-upload"),
                {"file": upload_file},
                format="multipart",
            )

            # Check DB content
            assert response.status_code == 200
            body = response.json()
            assert Dataset.objects.filter(
                id=body["dataset_id"], title="Uploaded via API"
            ).exists()

            # Check resource files has been created - can't check hash here
            assert (tmp_path / "index.json").exists()
            assert (tmp_path / "hashes.json").exists()

            with open(tmp_path / "index.json") as index_file:
                index = json.load(index_file)
                assert len(index) == 1
                assert index[0]["dataset_title"] == "Uploaded via API"

    def test_upload_multiple_datasets(self, tmp_path, api_client_with_token, db):

        with override_settings(MEDIA_ROOT=tmp_path, DEBUG=True):
            dataset_id = range(1, 6)
            for this_id_and_count in dataset_id:
                # Bulky to update zenodo id via base_dataset_json so do it directly
                data = base_dataset_json(title=f"Dataset {this_id_and_count}")
                data["zenodo"]["id"] = 100000 + this_id_and_count
                upload_file = self._upload_file(data)

                api_client_with_token.post(
                    reverse("api:datasets-upload"),
                    {"file": upload_file},
                    format="multipart",
                )

                assert Dataset.objects.count() == this_id_and_count

                with open(tmp_path / "index.json") as index_file:
                    index = json.load(index_file)
                    assert len(index) == this_id_and_count
                    titles = {ds["dataset_title"] for ds in index}

                    assert titles == {
                        f"Dataset {i}" for i in range(1, this_id_and_count + 1)
                    }

    def test_reuploading_same_zenodo_record_id_updates_in_place(
        self, tmp_path, api_client_with_token, db
    ):
        first_file = self._upload_file(base_dataset_json(title="Original"))
        second_file = self._upload_file(base_dataset_json(title="Corrected"))

        with override_settings(MEDIA_ROOT=tmp_path, DEBUG=True):
            first_response = api_client_with_token.post(
                reverse("api:datasets-upload"), {"file": first_file}, format="multipart"
            )
            original_id = first_response.json()["dataset_id"]

            # Check index
            with open(tmp_path / "index.json") as index_file:
                index = json.load(index_file)
                assert len(index) == 1
                assert index[0]["dataset_title"] == "Original"

            second_response = api_client_with_token.post(
                reverse("api:datasets-upload"),
                {"file": second_file},
                format="multipart",
            )

            assert second_response.status_code == 200
            assert second_response.json()["dataset_id"] == original_id
            assert Dataset.objects.count() == 1
            assert Dataset.objects.get().title == "Corrected"

            # Recheck index
            with open(tmp_path / "index.json") as index_file:
                index = json.load(index_file)
                assert len(index) == 1
                assert index[0]["dataset_title"] == "Corrected"

    def test_rejects_missing_required_field(self, api_client_with_token, db):
        data = base_dataset_json()
        del data["title"]
        upload_file = self._upload_file(data)

        response = api_client_with_token.post(
            reverse("api:datasets-upload"), {"file": upload_file}, format="multipart"
        )

        assert response.status_code == 400
        assert "detail" in response.json()
        assert Dataset.objects.count() == 0

    def test_rejects_invalid_json(self, api_client_with_token, db):
        upload_file = SimpleUploadedFile(
            "bad.json", b"{not valid json", content_type="application/json"
        )
        response = api_client_with_token.post(
            reverse("api:datasets-upload"), {"file": upload_file}, format="multipart"
        )

        assert response.status_code == 400
        assert "detail" in response.json()

    def test_requires_a_file(self, api_client_with_token, db):
        response = api_client_with_token.post(
            reverse("api:datasets-upload"), {}, format="multipart"
        )

        assert response.status_code == 400
