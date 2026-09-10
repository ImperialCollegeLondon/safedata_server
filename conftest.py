
import pytest
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from datasets.models import (
    Dataset,
    DatasetAuthors,
    DatasetFields,
    DatasetWorksheets,
    Locations,
    Taxa,
)
from gazetteer.models import Gazetteer, GazetteerAlias


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

@pytest.fixture
def api_client_with_token(db):
    user = User.objects.create_user(username="uploader", password="testpass123")
    token = Token.objects.create(user=user)
 
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return client


@pytest.fixture
def sample_aliases(db, sample_gazetteer):
    camp_a = Gazetteer.objects.get(location="River Camp A")
    GazetteerAlias.objects.create(location=camp_a, alias="Camp A Alt Name")
    GazetteerAlias.objects.create(location=camp_a, alias="1")


@pytest.fixture
def dataset_a(db, sample_gazetteer):
    """A dataset with an author, a keyword, a worksheet/field, taxa, and
    a location resolved to River Camp A."""
    dataset = Dataset.objects.create(
        zenodo_record_id=5000001,
        zenodo_concept_id=5000001,
        zenodo_publication_date="2020-01-01",
        title="Ant diversity in old-growth forest",
        description="A study of forest ants.",
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
        name="River Camp A",
        gazetteer_location=Gazetteer.objects.get(location="River Camp A"),
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
        access="Open",
        validator_version="3.1.1",
        temporal_extent_start="2018-01-01",
        temporal_extent_end="2018-12-31",
    )
    DatasetAuthors.objects.create(dataset=dataset, name="Riutta, Terhi")
    Locations.objects.create(
        dataset=dataset,
        name="River Camp B",
        gazetteer_location=Gazetteer.objects.get(location="River Camp B"),
    )
    return dataset


@pytest.fixture
def dataset_with_gbif_taxa(db):
    dataset = Dataset.objects.create(
        zenodo_record_id=7000001,
        zenodo_concept_id=7000001,
        zenodo_publication_date="2020-01-01",
        title="First GBIF dataset",
        description="",
        access="Open",
        validator_version="3.1.1",
    )
    Taxa.objects.create(
        dataset=dataset,
        source=Taxa.SOURCE_GBIF,
        taxon_id=100,
        parent_id=1,
        taxon_name="Formicidae",
        taxon_rank="family",
    )
    # A "user"-status unmatched taxon - taxon_id -1, not a real
    # identifier, must never be deduplicated with any other -1 entry.
    Taxa.objects.create(
        dataset=dataset,
        source=Taxa.SOURCE_GBIF,
        taxon_id=-1,
        parent_id=100,
        taxon_name="Formicidae",
        taxon_rank="morphospecies",
        taxon_status="user",
        worksheet_name="Ant morph 1",
    )
    return dataset
 
 
@pytest.fixture
def second_dataset_sharing_gbif_taxon(db):
    """A second dataset that references the same real GBIF taxon
    (taxon_id=100) as dataset_with_gbif_taxa - should collapse into one
    global entry referencing both datasets."""
    dataset = Dataset.objects.create(
        zenodo_record_id=7000002,
        zenodo_concept_id=7000002,
        zenodo_publication_date="2021-01-01",
        title="Second GBIF dataset",
        description="",
        access="Open",
        validator_version="3.1.1",
    )
    Taxa.objects.create(
        dataset=dataset,
        source=Taxa.SOURCE_GBIF,
        taxon_id=100,
        parent_id=1,
        taxon_name="Formicidae",
        taxon_rank="family",
    )
    # A separate unmatched taxon, also -1, in a different dataset - must
    # not be merged with the other dataset's -1 entry either.
    Taxa.objects.create(
        dataset=dataset,
        source=Taxa.SOURCE_GBIF,
        taxon_id=-1,
        parent_id=100,
        taxon_name="Formicidae",
        taxon_rank="morphospecies",
        taxon_status="user",
        worksheet_name="Ant morph A",
    )
    return dataset
 
 
@pytest.fixture
def dataset_with_sequence_taxa(db):
    dataset = Dataset.objects.create(
        zenodo_record_id=7000003,
        zenodo_concept_id=7000003,
        zenodo_publication_date="2020-06-01",
        title="Sequence dataset",
        description="",
        access="Open",
        validator_version="3.1.1",
    )
    Taxa.objects.create(
        dataset=dataset,
        source=Taxa.SOURCE_SEQUENCE,
        taxon_id=-1,
        parent_id=None,
        taxon_name="Fungi",
        taxon_rank="kingdom",
        taxon_status="loaded",
        database_name="UNITE",
    )
    return dataset
 
 
@pytest.fixture
def second_dataset_sharing_sequence_rank_name(db):
    """A second dataset whose sequence taxa share the same
    (rank, name) as dataset_with_sequence_taxa - should collapse into
    one global entry, since name/rank is the only usable identity for
    sequence taxa (their taxon_id is always a local placeholder)."""
    dataset = Dataset.objects.create(
        zenodo_record_id=7000004,
        zenodo_concept_id=7000004,
        zenodo_publication_date="2021-06-01",
        title="Second sequence dataset",
        description="",
        access="Open",
        validator_version="3.1.1",
    )
    Taxa.objects.create(
        dataset=dataset,
        source=Taxa.SOURCE_SEQUENCE,
        taxon_id=-1,
        parent_id=None,
        taxon_name="Fungi",
        taxon_rank="kingdom",
        taxon_status="loaded",
        database_name="UNITE",
    )
    return dataset