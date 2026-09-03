"""Tests for the concept versions endpoint (show_concepts equivalent)."""

import datetime

from django.urls import reverse

from datasets.models import Dataset


class TestConceptVersions:
    def test_single_open_version_is_most_recent(self, client, db):
        Dataset.objects.create(
            zenodo_record_id=8000001,
            zenodo_concept_id=8000001,
            zenodo_publication_date="2020-01-01",
            title="Single version dataset",
            description="",
            access="Open",
            validator_version="3.1.1",
        )

        response = client.get(reverse("api:concept-versions", args=[8000001]))
        body = response.json()

        assert body["zenodo_concept_id"] == 8000001
        assert body["title"] == "Single version dataset"
        assert len(body["versions"]) == 1
        assert body["versions"][0]["status"] == "*"

    def test_multiple_versions_only_newest_is_starred(self, client, db):
        Dataset.objects.create(
            zenodo_record_id=8000002,
            zenodo_concept_id=8000002,
            zenodo_publication_date="2019-01-01",
            title="Older title",
            description="",
            access="Open",
            validator_version="3.1.1",
        )
        Dataset.objects.create(
            zenodo_record_id=8000003,
            zenodo_concept_id=8000002,
            zenodo_publication_date="2021-01-01",
            title="Newer title",
            description="",
            access="Open",
            validator_version="3.1.1",
        )

        response = client.get(reverse("api:concept-versions", args=[8000002]))
        body = response.json()

        # Title shown is the most recent version's title.
        assert body["title"] == "Newer title"

        statuses = {v["zenodo_record_id"]: v["status"] for v in body["versions"]}
        assert statuses[8000003] == "*"
        assert statuses[8000002] == "o"

    def test_non_open_access_is_unavailable(self, client, db):
        Dataset.objects.create(
            zenodo_record_id=8000004,
            zenodo_concept_id=8000004,
            zenodo_publication_date="2020-01-01",
            title="Restricted dataset",
            description="",
            access="Closed",
            validator_version="3.1.1",
        )

        response = client.get(reverse("api:concept-versions", args=[8000004]))
        body = response.json()

        assert body["versions"][0]["status"] == "x"

    def test_future_embargo_date_is_unavailable_even_if_open(self, client, db):
        future_date = (datetime.date.today() + datetime.timedelta(days=30)).isoformat()
        Dataset.objects.create(
            zenodo_record_id=8000005,
            zenodo_concept_id=8000005,
            zenodo_publication_date="2020-01-01",
            title="Embargoed dataset",
            description="",
            access="Open",
            embargo_date=future_date,
            validator_version="3.1.1",
        )

        response = client.get(reverse("api:concept-versions", args=[8000005]))
        body = response.json()

        # Even though access is "Open", a future embargo date means
        # this version isn't actually available yet.
        assert body["versions"][0]["status"] == "x"

    def test_past_embargo_date_is_available(self, client, db):
        past_date = (datetime.date.today() - datetime.timedelta(days=30)).isoformat()
        Dataset.objects.create(
            zenodo_record_id=8000006,
            zenodo_concept_id=8000006,
            zenodo_publication_date="2020-01-01",
            title="Expired embargo dataset",
            description="",
            access="Open",
            embargo_date=past_date,
            validator_version="3.1.1",
        )

        response = client.get(reverse("api:concept-versions", args=[8000006]))
        body = response.json()

        # The embargo date has already passed, so this should be available.
        assert body["versions"][0]["status"] == "*"

    def test_unknown_concept_returns_404(self, client, db):
        response = client.get(reverse("api:concept-versions", args=[999999]))
        assert response.status_code == 404

    def test_versions_ordered_newest_first(self, client, db):
        Dataset.objects.create(
            zenodo_record_id=8000007,
            zenodo_concept_id=8000007,
            zenodo_publication_date="2019-01-01",
            title="v1",
            description="",
            access="Open",
            validator_version="3.1.1",
        )
        Dataset.objects.create(
            zenodo_record_id=8000008,
            zenodo_concept_id=8000007,
            zenodo_publication_date="2020-01-01",
            title="v2",
            description="",
            access="Open",
            validator_version="3.1.1",
        )
        Dataset.objects.create(
            zenodo_record_id=8000009,
            zenodo_concept_id=8000007,
            zenodo_publication_date="2021-01-01",
            title="v3",
            description="",
            access="Open",
            validator_version="3.1.1",
        )

        response = client.get(reverse("api:concept-versions", args=[8000007]))
        body = response.json()

        record_ids = [v["zenodo_record_id"] for v in body["versions"]]
        assert record_ids == [8000009, 8000008, 8000007]