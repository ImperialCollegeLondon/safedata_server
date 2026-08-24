from django.urls import path

from api.views.records import RecordMetadataView
from api.views.search import (
    AuthorSearchView,
    DateSearchView,
    FieldSearchView,
    SpatialSearchView,
    TaxaSearchView,
    TextSearchView,
)

app_name = "api"
 
urlpatterns = [
    path("search/text/", TextSearchView.as_view(), name="search-text"),
    path("search/authors/", AuthorSearchView.as_view(), name="search-authors"),
    path("search/dates/", DateSearchView.as_view(), name="search-dates"),
    path("search/fields/", FieldSearchView.as_view(), name="search-fields"),
    path("search/taxa/", TaxaSearchView.as_view(), name="search-taxa"),
    path("search/spatial/", SpatialSearchView.as_view(), name="search-spatial"),
    path("records/<int:zenodo_record_id>/", RecordMetadataView.as_view(), name="record-detail"),
]
 