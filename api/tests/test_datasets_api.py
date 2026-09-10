import json

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from datasets.models import Dataset
from datasets.tests import base_dataset_json


class TestDatasetUpload:
    def _upload_file(self, data):
        content = json.dumps(data).encode("utf-8")
        return SimpleUploadedFile("dataset.json", content, content_type="application/json")
 
    def test_requires_authentication(self, client, db):
        upload_file = self._upload_file(base_dataset_json())
        response = client.post(reverse("api:datasets-upload"), {"file": upload_file})
 
        assert response.status_code == 401
        assert Dataset.objects.count() == 0
 
    def test_succeeds_with_valid_token_and_creates_dataset(self, api_client_with_token, db):
        upload_file = self._upload_file(base_dataset_json(title="Uploaded via API"))
        response = api_client_with_token.post(
            reverse("api:datasets-upload"), {"file": upload_file}, format="multipart"
        )
 
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert Dataset.objects.filter(id=body["dataset_id"], title="Uploaded via API").exists()
 
    def test_reuploading_same_zenodo_record_id_updates_in_place(self, api_client_with_token, db):
        first_file = self._upload_file(base_dataset_json(title="Original"))
        first_response = api_client_with_token.post(
            reverse("api:datasets-upload"), {"file": first_file}, format="multipart"
        )
        original_id = first_response.json()["dataset_id"]
 
        second_file = self._upload_file(base_dataset_json(title="Corrected"))
        second_response = api_client_with_token.post(
            reverse("api:datasets-upload"), {"file": second_file}, format="multipart"
        )
 
        assert second_response.status_code == 200
        assert second_response.json()["dataset_id"] == original_id
        assert Dataset.objects.count() == 1
        assert Dataset.objects.get().title == "Corrected"
 
    def test_rejects_missing_required_field(self, api_client_with_token, db):
        data = base_dataset_json()
        del data["title"]
        upload_file = self._upload_file(data)
 
        response = api_client_with_token.post(
            reverse("api:datasets-upload"), {"file": upload_file}, format="multipart"
        )
 
        assert response.status_code == 400
        assert "error" in response.json()
        assert Dataset.objects.count() == 0
 
    def test_rejects_invalid_json(self, api_client_with_token, db):
        upload_file = SimpleUploadedFile(
            "bad.json", b"{not valid json", content_type="application/json"
        )
        response = api_client_with_token.post(
            reverse("api:datasets-upload"), {"file": upload_file}, format="multipart"
        )
 
        assert response.status_code == 400
        assert "error" in response.json()
 
    def test_requires_a_file(self, api_client_with_token, db):
        response = api_client_with_token.post(
            reverse("api:datasets-upload"), {}, format="multipart"
        )
 
        assert response.status_code == 400