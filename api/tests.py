"""Tests for the search API: shared ids/most_recent restriction logic,
and each of the six search endpoints."""

import pytest
from datasets.models import (
    Dataset,
    DatasetAuthors,
    DatasetFields,
    DatasetWorksheets,
    Locations,
    Taxa,
)
from django.urls import reverse
from gazetteer.models import Gazetteer

# --- Shared fixtures ---------------------------------------------------------

@pytest.fixture
def sample_gazetteer(db):
    Gazetteer.objects.create(
        location="Camp Alpha",
        geom_wgs84="POINT (117.6194 4.7461)",
        geom_local="POINT (568690.28 524629.41)",
    )
    Gazetteer.objects.create(
        location="Camp Beta",
        geom_wgs84="POINT (117.6231 4.7502)",
        geom_local="POINT (569100.22 525083.00)",
    )


@pytest.fixture
def dataset_a(db, sample_gazetteer):
    """A dataset with an author, a keyword, a worksheet/field, taxa, and
    a location resolved to Camp Alpha."""
    dataset = Dataset.objects.create(
        zenodo_record_id=5000001,
        zenodo_concept_id=5000001,
        zenodo_publication_date="2020-01-01",
        title="Ant diversity in old-growth forest",
        description="A study of forest ants.",
        filename="ants.xlsx",
        access="Open",
        validator_version="3.1.1",
        temporal_extent_start="2014-01-01",
        temporal_extent_end="2014-12-31",
    )
    DatasetAuthors.objects.create(dataset=dataset, name="Ewers, Robert")
    worksheet = DatasetWorksheets.objects.create(
        dataset=dataset, name="data", max_row=10, max_col=2
    )
    DatasetFields.objects.create(
        worksheet=worksheet,
        field_name="Temperature",
        description="Air temperature reading",
        field_type="numeric",
        col_idx=1,
    )
    Taxa.objects.create(
        dataset=dataset,
        source=Taxa.SOURCE_GBIF,
        taxon_id=100,
        taxon_name="Formicidae",
        taxon_rank="family",
    )
    Locations.objects.create(
        dataset=dataset,
        name="Camp Alpha",
        gazetteer_location=Gazetteer.objects.get(location="Camp Alpha"),
    )
    return dataset


@pytest.fixture
def dataset_b(db, sample_gazetteer):
    """A second, unrelated dataset - different author, no overlapping
    keywords/taxa, a different date range and location."""
    dataset = Dataset.objects.create(
        zenodo_record_id=5000002,
        zenodo_concept_id=5000002,
        zenodo_publication_date="2021-06-01",
        title="Soil carbon flux measurements",
        description="Carbon dioxide flux from soil respiration.",
        filename="carbon.xlsx",
        access="Open",
        validator_version="3.1.1",
        temporal_extent_start="2018-01-01",
        temporal_extent_end="2018-12-31",
    )
    DatasetAuthors.objects.create(dataset=dataset, name="Riutta, Terhi")
    Locations.objects.create(
        dataset=dataset,
        name="Camp Beta",
        gazetteer_location=Gazetteer.objects.get(location="Camp Beta"),
    )
    return dataset


class TestSharedRestriction:
    def test_ids_restricts_to_given_records(self, client, dataset_a, dataset_b):
        response = client.get(
            reverse("api:search-text"), {"text": "forest", "ids": dataset_b.zenodo_record_id}
        )
        # dataset_a matches "forest" in its title, but ids restricts to
        # dataset_b only, which doesn't match "forest" at all.
        assert response.json()["count"] == 0

    def test_most_recent_restricts_to_latest_version(self, client, db):
        Dataset.objects.create(
            zenodo_record_id=6000001,
            zenodo_concept_id=6000001,
            zenodo_publication_date="2020-01-01",
            title="Outdated version",
            description="",
            filename="a.xlsx",
            access="Open",
            validator_version="3.1.1",
        )
        Dataset.objects.create(
            zenodo_record_id=6000002,
            zenodo_concept_id=6000001,
            zenodo_publication_date="2021-01-01",
            title="Newer version",
            description="",
            filename="a.xlsx",
            access="Open",
            validator_version="3.1.1",
        )

        response = client.get(reverse("api:search-text"), {"text": "version", "most_recent": ""})

        assert response.json()["count"] == 1
        assert response.json()["entries"][0]["zenodo_record_id"] == 6000002

    def test_invalid_ids_returns_400(self, client, dataset_a):
        response = client.get(reverse("api:search-text"), {"text": "forest", "ids": "not-a-number"})
        assert response.status_code == 400


class TestTextSearch:
    def test_matches_title(self, client, dataset_a, dataset_b):
        response = client.get(reverse("api:search-text"), {"text": "forest"})
        assert response.json()["count"] == 1
        assert response.json()["entries"][0]["zenodo_record_id"] == dataset_a.zenodo_record_id

    def test_matches_field_description(self, client, dataset_a, dataset_b):
        response = client.get(reverse("api:search-text"), {"text": "temperature"})
        assert response.json()["count"] == 1

    def test_missing_text_returns_400(self, client, db):
        response = client.get(reverse("api:search-text"))
        assert response.status_code == 400


class TestAuthorSearch:
    def test_partial_name_match(self, client, dataset_a, dataset_b):
        response = client.get(reverse("api:search-authors"), {"name": "Ewers"})
        assert response.json()["count"] == 1
        assert response.json()["entries"][0]["zenodo_record_id"] == dataset_a.zenodo_record_id

    def test_no_match_returns_empty(self, client, dataset_a):
        response = client.get(reverse("api:search-authors"), {"name": "Nobody"})
        assert response.json()["count"] == 0


class TestDateSearch:
    def test_single_date_within_extent(self, client, dataset_a, dataset_b):
        response = client.get(reverse("api:search-dates"), {"date": "2014-06-01"})
        assert response.json()["count"] == 1
        assert response.json()["entries"][0]["zenodo_record_id"] == dataset_a.zenodo_record_id

    def test_intersect_match_type(self, client, dataset_a, dataset_b):
        response = client.get(
            reverse("api:search-dates"), {"date": "2014-06-01,2018-06-01"}
        )
        assert response.json()["count"] == 2

    def test_contain_match_type_matches_spanning_dataset(self, client, dataset_a, dataset_b):
        # dataset_a spans all of 2014. A narrow query range inside that
        # extent should match under "contain" semantics.
        response = client.get(
            reverse("api:search-dates"),
            {"date": "2014-03-01,2014-06-01", "match_type": "contain"},
        )
        assert response.json()["count"] == 1
        assert response.json()["entries"][0]["zenodo_record_id"] == dataset_a.zenodo_record_id


    def test_contain_match_type_excludes_partial_overlap(self, client, dataset_a, dataset_b):
        # This range starts inside dataset_a's extent but extends past it -
        # an "intersect" search would match, but "contain" requires the
        # dataset's own extent to fully span the query range, so it should not.
        response = client.get(
            reverse("api:search-dates"),
            {"date": "2014-06-01,2015-06-01", "match_type": "contain"},
        )
        assert response.json()["count"] == 0

    def test_invalid_match_type_returns_400(self, client, dataset_a):
        response = client.get(
            reverse("api:search-dates"), {"date": "2014-01-01", "match_type": "bogus"}
        )
        assert response.status_code == 400

    def test_missing_date_returns_400(self, client, db):
        response = client.get(reverse("api:search-dates"))
        assert response.status_code == 400


class TestFieldSearch:
    def test_matches_field_type(self, client, dataset_a, dataset_b):
        response = client.get(reverse("api:search-fields"), {"field_type": "numeric"})
        assert response.json()["count"] == 1

    def test_no_params_returns_400(self, client, db):
        response = client.get(reverse("api:search-fields"))
        assert response.status_code == 400


class TestTaxaSearch:
    def test_matches_taxon_name(self, client, dataset_a, dataset_b):
        response = client.get(reverse("api:search-taxa"), {"name": "Formicidae"})
        assert response.json()["count"] == 1

    def test_matches_source(self, client, dataset_a, dataset_b):
        response = client.get(reverse("api:search-taxa"), {"source": "gbif"})
        assert response.json()["count"] == 1

    def test_invalid_source_returns_400(self, client, dataset_a):
        response = client.get(reverse("api:search-taxa"), {"source": "not-a-source"})
        assert response.status_code == 400

    def test_no_params_returns_400(self, client, db):
        response = client.get(reverse("api:search-taxa"))
        assert response.status_code == 400


class TestSpatialSearch:
    def test_location_match_unbuffered(self, client, dataset_a, dataset_b):
        response = client.get(reverse("api:search-spatial"), {"location": "Camp Alpha"})
        assert response.json()["count"] == 1
        assert response.json()["entries"][0]["zenodo_record_id"] == dataset_a.zenodo_record_id

    def test_location_with_buffer_finds_nearby(self, client, dataset_a, dataset_b):
        # Camp Alpha and Camp Beta are a few hundred metres apart - a
        # large buffer should catch both datasets.
        response = client.get(
            reverse("api:search-spatial"), {"location": "Camp Alpha", "distance": "5000"}
        )
        assert response.json()["count"] == 2

    def test_unknown_location_returns_400(self, client, db):
        response = client.get(reverse("api:search-spatial"), {"location": "Nowhere"})
        assert response.status_code == 400

    def test_both_wkt_and_location_returns_400(self, client, db):
        response = client.get(
            reverse("api:search-spatial"),
            {"location": "Camp Alpha", "wkt": "POINT (117.6 4.7)"},
        )
        assert response.status_code == 400

    def test_neither_wkt_nor_location_returns_400(self, client, db):
        response = client.get(reverse("api:search-spatial"))
        assert response.status_code == 400

    def test_wkt_far_away_returns_empty(self, client, dataset_a, dataset_b):
        response = client.get(
            reverse("api:search-spatial"), {"wkt": "POINT (0 0)", "distance": "100"}
        )
        assert response.json()["count"] == 0