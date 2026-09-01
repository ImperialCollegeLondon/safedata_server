from django.urls import path

from api.views.gazetteer import (
    GazetteerAliasUploadView,
    GazetteerUploadView,
    gazetteer_aliases_download,
    gazetteer_aliases_hash,
    gazetteer_download,
    gazetteer_hash,
)
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
    path("gazetteer/download/", gazetteer_download, name="gazetteer-download"),
    path("gazetteer/hash/", gazetteer_hash, name="gazetteer-hash"),
    path("gazetteer/upload/", GazetteerUploadView.as_view(), name="gazetteer-upload"),
    path("gazetteer/aliases/download/", gazetteer_aliases_download, name="gazetteer-alias-download"),
    path("gazetteer/aliases/hash/", gazetteer_aliases_hash, name="gazetteer-alias-hash"),
    path("gazetteer/aliases/upload/", GazetteerAliasUploadView.as_view(), name="gazetteer-alias-upload"),
    path("records/<int:zenodo_record_id>/", RecordMetadataView.as_view(), name="record-detail"),
]
 