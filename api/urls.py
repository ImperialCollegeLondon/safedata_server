from django.urls import path

from api.views.datasets import (
    DatasetUploadView,
    dataset_index_download,
    dataset_index_hash,
)
from api.views.gazetteer import (
    GazetteerAliasUploadView,
    GazetteerUploadView,
    gazetteer_aliases_download,
    gazetteer_aliases_hash,
    gazetteer_download,
    gazetteer_hash,
)
from api.views.records import ConceptVersionsView, RecordMetadataView
from api.views.search import (
    AuthorSearchView,
    DateSearchView,
    FieldSearchView,
    SpatialSearchView,
    TaxaSearchView,
    TextSearchView,
)
from api.views.taxa import (
    GlobalGbifTaxonCoverageView,
    GlobalSequenceTaxonCoverageView,
    RecordTaxaView,
)

app_name = "api"
 
urlpatterns = [
    # URLs for searching datasets and gazetteer locations:
    path("search/text/", TextSearchView.as_view(), name="search-text"),
    path("search/authors/", AuthorSearchView.as_view(), name="search-authors"),
    path("search/dates/", DateSearchView.as_view(), name="search-dates"),
    path("search/fields/", FieldSearchView.as_view(), name="search-fields"),
    path("search/taxa/", TaxaSearchView.as_view(), name="search-taxa"),
    path("search/spatial/", SpatialSearchView.as_view(), name="search-spatial"),
    # URLs for downloading and uploading datasets and gazetteer locations:
    path("gazetteer/download/", gazetteer_download, name="gazetteer-download"),
    path("gazetteer/hash/", gazetteer_hash, name="gazetteer-hash"),
    path("gazetteer/upload/", GazetteerUploadView.as_view(), name="gazetteer-upload"),
    path("gazetteer/aliases/download/", gazetteer_aliases_download, name="gazetteer-alias-download"),
    path("gazetteer/aliases/hash/", gazetteer_aliases_hash, name="gazetteer-alias-hash"),
    path("gazetteer/aliases/upload/", GazetteerAliasUploadView.as_view(), name="gazetteer-alias-upload"),
    # URLs for downloading and uploading datasets:
    path("datasets/upload/", DatasetUploadView.as_view(), name="datasets-upload"),
    path("datasets/index/download/", dataset_index_download, name="datasets-index-download"),
    path("datasets/index/hash/", dataset_index_hash, name="datasets-index-hash"),
    # URL for retrieving metadata for a specific Zenodo record:
    path("records/<int:zenodo_record_id>/", RecordMetadataView.as_view(), name="record-detail"),
    path("concepts/<int:zenodo_concept_id>/", ConceptVersionsView.as_view(), name="concept-versions"),
    # Taxa coverage endpoints:
    path("taxon_coverage/gbif/", GlobalGbifTaxonCoverageView.as_view(), name="taxon-coverage-gbif"),
    path("taxon_coverage/sequence/", GlobalSequenceTaxonCoverageView.as_view(), name="taxon-coverage-sequence"),
    path("records/<int:zenodo_record_id>/taxa/", RecordTaxaView.as_view(), name="record-taxa"),
]
 