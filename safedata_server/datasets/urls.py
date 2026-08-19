from django.urls import path

from datasets.views import (
    dataset_detail,
    dataset_index_download,
    dataset_index_hash,
    dataset_list,
)

app_name = "datasets"

urlpatterns = [
    path("", dataset_list, name="list"),
    path("index/download/", dataset_index_download, name="index-download"),
    path("index/hash/", dataset_index_hash, name="index-hash"),
    path("<int:pk>/", dataset_detail, name="detail"),
]