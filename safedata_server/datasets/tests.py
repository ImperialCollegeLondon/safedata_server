"""Tests for datasets.ingest: creating, updating, and validating datasets
from safedata_validator JSON exports."""

import pytest
from django.contrib.gis.geos import Point

from gazetteer.models import Gazetteer, GazetteerAlias

from .ingest import DatasetIngestError, ingest_dataset
from .models import Dataset, DatasetFields, Locations, Taxa


# --- Shared fixtures ---------------------------------------------------------

@pytest.fixture
def sample_gazetteer(db):
    Gazetteer.objects.create(
        location="River Camp A",
        geom_wgs84="POINT (117.6194 4.7461)",
        geom_local="POINT (568690.28 524629.41)",
    )
    Gazetteer.objects.create(
        location="River Camp B",
        geom_wgs84="POINT (117.6231 4.7502)",
        geom_local="POINT (569100.22 525083.00)",
    )


def base_dataset_json(**overrides):
    """A minimal valid dataset export, with every field this app actually
    requires. Individual tests override specific keys to test variations."""
    data = {
        "zenodo_record_id": 1000001,
        "zenodo_concept_id": 1000001,
        "zenodo_publication_date": "2024-01-15",
        "title": "Test Dataset",
        "description": "A dataset for testing.",
        "filename": "test_dataset.xlsx",
        "access": "Open",
        "embargo_date": None,
        "access_conditions": None,
        "validator_version": "3.1.1",
        "gbif_timestamp": None,
        "project_ids": [],
        "authors": [],
        "funders": [],
        "permits": [],
        "keywords": [],
        "dataworksheets": [],
        "gbif_taxa": [],
        "sequenced_taxa": {},
        "locations": [],
        "temporal_extent": None,
        "latitudinal_extent": None,
        "longitudinal_extent": None,
    }
    data.update(overrides)
    return data


class TestIngestDatasetCore:
    def test_creates_dataset_with_correct_fields(self, db):
        data = base_dataset_json(
            title="Real Title",
            temporal_extent=["2014-10-01", "2018-09-01"],
            latitudinal_extent=[4.64, 4.95],
            longitudinal_extent=[116.95, 117.79],
        )

        dataset = ingest_dataset(data)

        assert dataset.title == "Real Title"
        assert dataset.zenodo_record_id == 1000001
        assert dataset.temporal_extent_start.isoformat() == "2014-10-01"
        assert dataset.temporal_extent_end.isoformat() == "2018-09-01"
        assert dataset.latitudinal_extent_min == 4.64
        assert dataset.longitudinal_extent_max == 117.79

    def test_missing_zenodo_record_id_raises(self, db):
        data = base_dataset_json()
        del data["zenodo_record_id"]

        with pytest.raises(DatasetIngestError):
            ingest_dataset(data)

    def test_missing_title_raises(self, db):
        data = base_dataset_json()
        del data["title"]

        with pytest.raises(DatasetIngestError):
            ingest_dataset(data)

    def test_invalid_date_raises(self, db):
        data = base_dataset_json(embargo_date="not-a-date")

        with pytest.raises(DatasetIngestError):
            ingest_dataset(data)

    def test_missing_dataset_fails_atomically(self, db):
        """A failure partway through ingestion should roll back the whole
        thing - no orphaned Dataset row left behind."""
        data = base_dataset_json(
            locations=[{"name": "Nonexistent Location", "new_location": False, "wkt_wgs84": "NOT WKT"}]
        )

        with pytest.raises(DatasetIngestError):
            ingest_dataset(data)

        assert Dataset.objects.count() == 0


class TestIngestDatasetVersioning:
    def test_reingesting_same_zenodo_record_id_updates_in_place(self, db):
        first = ingest_dataset(base_dataset_json(title="Original Title"))
        original_pk = first.id

        second = ingest_dataset(base_dataset_json(title="Corrected Title"))

        assert second.id == original_pk
        assert Dataset.objects.count() == 1
        assert Dataset.objects.get().title == "Corrected Title"

    def test_reingesting_clears_and_rebuilds_children(self, db):
        first_data = base_dataset_json(keywords=["old-keyword"])
        dataset = ingest_dataset(first_data)
        assert dataset.keywords.count() == 1

        second_data = base_dataset_json(keywords=["new-keyword-1", "new-keyword-2"])
        dataset = ingest_dataset(second_data)

        assert dataset.keywords.count() == 2
        assert set(dataset.keywords.values_list("keyword", flat=True)) == {
            "new-keyword-1",
            "new-keyword-2",
        }

    def test_reingesting_preserves_dataset_scoped_aliases(self, db, sample_gazetteer):
        """The whole reason Dataset is updated in place rather than
        deleted and recreated: a dataset-scoped GazetteerAlias must
        survive the dataset being corrected/re-ingested."""
        dataset = ingest_dataset(base_dataset_json())
        camp_a = Gazetteer.objects.get(location="River Camp A")
        GazetteerAlias.objects.create(location=camp_a, alias="Camp A Alt", dataset=dataset)

        ingest_dataset(base_dataset_json(title="Updated Title"))

        assert GazetteerAlias.objects.filter(alias="Camp A Alt").exists()


class TestIngestWorksheetsAndFields:
    def test_creates_worksheets_and_fields(self, db):
        data = base_dataset_json(
            dataworksheets=[
                {
                    "name": "data",
                    "title": "Main data",
                    "description": "The main worksheet.",
                    "max_row": 100,
                    "max_col": 5,
                    "field_name_row": 1,
                    "n_data_row": 99,
                    "external": None,
                    "fields": [
                        {
                            "field_name": "SampleID",
                            "description": "Sample identifier",
                            "field_type": "id",
                            "units": None,
                            "method": None,
                            "levels": None,
                            "taxon_field": None,
                            "taxon_name": None,
                            "interaction_field": None,
                            "interaction_name": None,
                            "range": None,
                            "col_idx": 1,
                        }
                    ],
                }
            ]
        )

        dataset = ingest_dataset(data)

        assert dataset.worksheets.count() == 1
        worksheet = dataset.worksheets.get()
        assert worksheet.name == "data"
        assert DatasetFields.objects.filter(worksheet=worksheet).count() == 1
        field = DatasetFields.objects.get(worksheet=worksheet)
        assert field.field_name == "SampleID"
        assert field.col_idx == 1

    def test_missing_field_name_raises(self, db):
        data = base_dataset_json(
            dataworksheets=[
                {
                    "name": "data",
                    "max_row": 10,
                    "max_col": 1,
                    "fields": [{"field_type": "id", "col_idx": 1}],
                }
            ]
        )

        with pytest.raises(DatasetIngestError):
            ingest_dataset(data)


class TestIngestTaxa:
    def test_ingests_gbif_taxa(self, db):
        data = base_dataset_json(
            gbif_taxa=[
                {
                    "taxon_id": 12345,
                    "parent_id": None,
                    "taxon_name": "Panthera tigris",
                    "taxon_rank": "species",
                    "taxon_status": "accepted",
                    "worksheet_name": "data",
                }
            ]
        )

        dataset = ingest_dataset(data)

        assert dataset.taxa.count() == 1
        taxon = dataset.taxa.get()
        assert taxon.source == Taxa.SOURCE_GBIF
        assert taxon.taxon_name == "Panthera tigris"
        assert taxon.database_name is None

    def test_ingests_sequenced_taxa_with_group_metadata(self, db):
        data = base_dataset_json(
            sequenced_taxa={
                "SeqTaxa": {
                    "database_name": "UNITE",
                    "database_version": "version 7.2",
                    "database_link": "https://unite.ut.ee",
                    "taxon_index": [
                        {
                            "taxon_id": -1,
                            "parent_id": None,
                            "taxon_name": "Fungi",
                            "taxon_rank": "kingdom",
                            "taxon_status": "loaded",
                            "worksheet_name": None,
                        },
                        {
                            "taxon_id": -2,
                            "parent_id": -1,
                            "taxon_name": "Ascomycota",
                            "taxon_rank": "phylum",
                            "taxon_status": "loaded",
                            "worksheet_name": None,
                        },
                    ],
                }
            }
        )

        dataset = ingest_dataset(data)

        assert dataset.taxa.count() == 2
        for taxon in dataset.taxa.all():
            assert taxon.source == Taxa.SOURCE_SEQUENCE
            assert taxon.database_name == "UNITE"
            assert taxon.database_link == "https://unite.ut.ee"

    def test_no_taxa_data_ingests_cleanly(self, db):
        dataset = ingest_dataset(base_dataset_json(gbif_taxa=[], sequenced_taxa={}))

        assert dataset.taxa.count() == 0


class TestIngestLocations:
    def test_resolves_direct_gazetteer_match(self, db, sample_gazetteer):
        data = base_dataset_json(
            locations=[{"name": "River Camp A", "new_location": False, "wkt_wgs84": None}]
        )

        dataset = ingest_dataset(data)

        location = dataset.locations.get()
        assert location.gazetteer_location.location == "River Camp A"

    def test_resolves_dataset_scoped_alias(self, db, sample_gazetteer):
        camp_a = Gazetteer.objects.get(location="River Camp A")

        # First ingest with no aliases, to get a real Dataset to scope the
        # alias to, then register the alias, then re-ingest referencing it.
        dataset = ingest_dataset(base_dataset_json())
        GazetteerAlias.objects.create(location=camp_a, alias="Camp A Nickname", dataset=dataset)

        data = base_dataset_json(
            locations=[{"name": "Camp A Nickname", "new_location": False, "wkt_wgs84": None}]
        )
        dataset = ingest_dataset(data)

        location = dataset.locations.get()
        assert location.gazetteer_location.location == "River Camp A"

    def test_resolves_general_alias(self, db, sample_gazetteer):
        camp_b = Gazetteer.objects.get(location="River Camp B")
        GazetteerAlias.objects.create(location=camp_b, alias="Camp B General", dataset=None)

        data = base_dataset_json(
            locations=[{"name": "Camp B General", "new_location": False, "wkt_wgs84": None}]
        )
        dataset = ingest_dataset(data)

        location = dataset.locations.get()
        assert location.gazetteer_location.location == "River Camp B"

    def test_unresolved_new_location_stores_own_geometry(self, db, sample_gazetteer):
        data = base_dataset_json(
            locations=[
                {
                    "name": "Brand New Site",
                    "new_location": True,
                    "wkt_wgs84": "POINT (117.7 4.8)",
                }
            ]
        )

        dataset = ingest_dataset(data)

        location = dataset.locations.get()
        assert location.gazetteer_location is None
        assert location.new_location is True
        assert location.geom_wgs84 == Point(117.7, 4.8, srid=4326)

    def test_invalid_wkt_raises(self, db, sample_gazetteer):
        data = base_dataset_json(
            locations=[
                {"name": "Bad Geometry Site", "new_location": True, "wkt_wgs84": "NOT WKT"}
            ]
        )

        with pytest.raises(DatasetIngestError):
            ingest_dataset(data)