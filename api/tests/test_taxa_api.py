from django.urls import reverse

from datasets.models import Dataset, Taxa


class TestGlobalGbifCoverage:
    def test_deduplicates_real_taxon_id_across_datasets(
        self, client, dataset_with_gbif_taxa, second_dataset_sharing_gbif_taxon
    ):
        response = client.get(reverse("api:taxon-coverage-gbif"))
        body = response.json()
 
        matching = [t for t in body["taxa"] if t["taxon_id"] == 100]
        assert len(matching) == 1
        assert sorted(matching[0]["zenodo_record_ids"]) == [7000001, 7000002]
 
    def test_never_deduplicates_unmatched_taxon_id(
        self, client, dataset_with_gbif_taxa, second_dataset_sharing_gbif_taxon
    ):
        response = client.get(reverse("api:taxon-coverage-gbif"))
        body = response.json()
 
        unmatched = [t for t in body["taxa"] if t["taxon_id"] == -1]
        # Two separate -1 entries from two different datasets must stay
        # separate, not collapse into one.
        assert len(unmatched) == 2
        record_ids = sorted(t["zenodo_record_ids"][0] for t in unmatched)
        assert record_ids == [7000001, 7000002]
 
    def test_only_includes_gbif_source(self, client, dataset_with_sequence_taxa):
        response = client.get(reverse("api:taxon-coverage-gbif"))
        body = response.json()
        assert body["count"] == 0
 
 
class TestGlobalSequenceCoverage:
    def test_groups_by_rank_and_name_across_datasets(
        self,
        client,
        dataset_with_sequence_taxa,
        second_dataset_sharing_sequence_rank_name,
    ):
        response = client.get(reverse("api:taxon-coverage-sequence"))
        body = response.json()
 
        assert body["count"] == 1
        entry = body["taxa"][0]
        assert entry["taxon_name"] == "Fungi"
        assert sorted(entry["zenodo_record_ids"]) == [7000003, 7000004]
 
    def test_only_includes_sequence_source(self, client, dataset_with_gbif_taxa):
        response = client.get(reverse("api:taxon-coverage-sequence"))
        body = response.json()
        assert body["count"] == 0
 
 
class TestRecordTaxa:
    def test_auto_detects_gbif_source(self, client, dataset_with_gbif_taxa):
        response = client.get(
            reverse("api:record-taxa", args=[dataset_with_gbif_taxa.zenodo_record_id])
        )
        body = response.json()
 
        assert body["source"] == Taxa.SOURCE_GBIF
        assert body["count"] == 2
 
    def test_auto_detects_sequence_source(self, client, dataset_with_sequence_taxa):
        response = client.get(
            reverse("api:record-taxa", args=[dataset_with_sequence_taxa.zenodo_record_id])
        )
        body = response.json()
 
        assert body["source"] == Taxa.SOURCE_SEQUENCE
        assert body["count"] == 1
 
    def test_no_taxa_returns_empty_with_null_source(self, client, db):
        dataset = Dataset.objects.create(
            zenodo_record_id=7000005,
            zenodo_concept_id=7000005,
            zenodo_publication_date="2020-01-01",
            title="No taxa dataset",
            description="",
            access="Open",
            validator_version="3.1.1",
        )
        response = client.get(reverse("api:record-taxa", args=[dataset.zenodo_record_id]))
        body = response.json()
 
        assert body == {"count": 0, "taxa": [], "source": None}
 
    def test_unknown_record_returns_404(self, client, db):
        response = client.get(reverse("api:record-taxa", args=[999999]))
        assert response.status_code == 404
 
    def test_does_not_leak_other_datasets_taxa(
        self, client, dataset_with_gbif_taxa, second_dataset_sharing_gbif_taxon
    ):
        """A per-record request should only ever return that record's own
        taxa, never another dataset's, even if they share a taxon_id."""
        response = client.get(
            reverse("api:record-taxa", args=[dataset_with_gbif_taxa.zenodo_record_id])
        )
        body = response.json()
 
        for entry in body["taxa"]:
            assert entry["zenodo_record_ids"] == [dataset_with_gbif_taxa.zenodo_record_id]