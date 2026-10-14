import json

import django_tables2 as tables
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.html import format_html

from .ingest import DatasetIngestError, ingest_dataset
from .models import Dataset


@login_required
def dataset_upload_page(request):
    """A simple browser-based upload page for a dataset JSON export,
    alongside the existing token-authenticated API endpoint."""
    if request.method == "POST":
        uploaded_file = request.FILES.get("file")

        if uploaded_file is None:
            messages.error(request, "No dataset file was provided.")
            return redirect("datasets:upload-page")

        try:
            data = json.load(uploaded_file)
            dataset = ingest_dataset(data)
        except (json.JSONDecodeError, DatasetIngestError) as exc:
            messages.error(request, f"Dataset upload failed: {exc}")
            return redirect("datasets:upload-page")

        messages.success(request, f'Dataset "{dataset.title}" uploaded successfully.')
        return redirect("datasets:upload-page")

    return render(request, "datasets/upload.html")


def dataset_list(request):
    """Searchable list of datasets. Shows only the latest version of each
    dataset by default (per zenodo_concept_id) - older versions remain
    reachable via the detail page of a search result, but aren't
    surfaced in the list itself.
    """
    query = request.GET.get("q", "").strip()

    datasets = Dataset.latest_versions().order_by("-zenodo_publication_date")

    if query:
        datasets = datasets.filter(
            Q(title__icontains=query)
            | Q(description__icontains=query)
            | Q(keywords__keyword__icontains=query)
            | Q(authors__name__icontains=query)
        ).distinct()

    context = {
        "datasets": datasets,
        "query": query,
    }
    return render(request, "datasets/list.html", context)


class VersionsTable(tables.Table):
    def __init__(self, *args, **kwargs):
        self.highlight_id = kwargs.pop("highlight_id", None)
        super().__init__(*args, **kwargs)

    def get_row_class(self, record):
        if self.highlight_id and record.zenodo_record_id == int(self.highlight_id):
            return "current-row"
        return ""

    class Meta:
        model = Dataset
        sequence = (
            "zenodo_record_id",
            "zenodo_publication_date",
            "access",
            "zenodo_record_doi",
        )
        exclude = (
            "id",
            "zenodo_concept_id",
            "zenodo_concept_doi",
            "title",
            "description",
            "embargo_date",
            "access_conditions",
            "validator_version",
            "gbif_timestamp",
            "temporal_extent_start",
            "temporal_extent_end",
            "latitudinal_extent_min",
            "latitudinal_extent_max",
            "longitudinal_extent_min",
            "longitudinal_extent_max",
        )
        orderable = False
        row_attrs = {"class": lambda table, record: table.get_row_class(record)}  # noqa: RUF012

    def render_zenodo_record_doi(self, record):
        """Render Zenodo links."""
        return format_html(
            '<a href="https://zenodo.org/records/{}">{}</a>',
            record.zenodo_record_id,
            record.zenodo_record_doi,
        )

    def render_zenodo_record_id(self, record):
        """Render internal links to dataset details."""

        return format_html(
            '<a href="{}">{}</a>',
            reverse("datasets:detail", args=[record.zenodo_record_id]),
            record.zenodo_record_id,
        )


def dataset_detail(request, zenodo_record_id):
    """Full metadata for one dataset."""
    dataset = get_object_or_404(
        Dataset.objects.prefetch_related(
            "authors",
            "funders",
            "permits",
            "keywords",
            "worksheets__fields",
            "projects",
            "files",
        ),
        zenodo_record_id=zenodo_record_id,
    )

    taxa_gbif_count = dataset.taxa.filter(source="gbif").count()
    taxa_sequence_count = dataset.taxa.filter(source="sequence").count()
    locations_resolved_count = dataset.locations.filter(
        gazetteer_location__isnull=False
    ).count()

    versions = Dataset.objects.filter(
        zenodo_concept_id=dataset.zenodo_concept_id
    ).order_by("-zenodo_publication_date")

    context = {
        "dataset": dataset,
        "taxa_gbif_count": taxa_gbif_count,
        "taxa_sequence_count": taxa_sequence_count,
        "locations_total_count": dataset.locations.count(),
        "locations_resolved_count": locations_resolved_count,
        "versions": VersionsTable(versions, highlight_id=dataset.zenodo_record_id),
    }
    return render(request, "datasets/detail.html", context)


def taxa_browse(request):
    """Browse the global taxon coverage across all datasets - GBIF and
    sequence-derived taxa shown separately (per taxon_coverage endpoints),
    since the two can't be meaningfully combined."""
    return render(request, "datasets/taxa.html")
