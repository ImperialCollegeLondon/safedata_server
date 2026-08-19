from django.urls import path

from datasets.views import dataset_detail, dataset_list

app_name = "datasets"

urlpatterns = [
    path("", dataset_list, name="list"),
    path("<int:pk>/", dataset_detail, name="detail"),
]