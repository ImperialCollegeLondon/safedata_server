from django.urls import path

from datasets.views import (
    dataset_detail,
    dataset_list,
    dataset_upload_page,
)

app_name = "datasets"

urlpatterns = [
    path("", dataset_list, name="list"),
    path("upload/", dataset_upload_page, name="upload-page"),
    path("<int:pk>/", dataset_detail, name="detail"),
]