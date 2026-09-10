from django.urls import path

from datasets.views import (
    dataset_detail,
    dataset_list,
    dataset_upload_page,
    taxa_browse,
)

app_name = "datasets"

urlpatterns = [
    path("", dataset_list, name="list"),
    path("upload/", dataset_upload_page, name="upload-page"),
    path("taxa/", taxa_browse, name="taxa"),
    path("<int:zenodo_record_id>/", dataset_detail, name="detail"),
]