from typing import ClassVar

from django.conf import settings
from django.contrib.gis.db import models as gis_models
from django.db import models
from django.db.models import OuterRef, Subquery


class Dataset(models.Model):
    """Top-level metadata for one dataset.

    Each version of a dataset (per Zenodo's versioning model) is its own
    complete Dataset entry in the database.
    """

    zenodo_record_id: models.IntegerField = models.IntegerField(
        unique=True
    )
    zenodo_concept_id: models.IntegerField = models.IntegerField()
    zenodo_publication_date: models.DateField = models.DateField()

    title: models.CharField = models.CharField(max_length=1000)
    description: models.TextField = models.TextField()

    access: models.CharField = models.CharField(max_length=50)
    embargo_date: models.DateField = models.DateField(null=True, blank=True)
    access_conditions: models.TextField = models.TextField(null=True, blank=True)

    validator_version: models.CharField = models.CharField(max_length=50)
    gbif_timestamp: models.DateField = models.DateField(null=True, blank=True)

    temporal_extent_start: models.DateField = models.DateField(null=True, blank=True)
    temporal_extent_end: models.DateField = models.DateField(null=True, blank=True)
    latitudinal_extent_min: models.FloatField = models.FloatField(null=True, blank=True)
    latitudinal_extent_max: models.FloatField = models.FloatField(null=True, blank=True)
    longitudinal_extent_min: models.FloatField = models.FloatField(null=True, blank=True)
    longitudinal_extent_max: models.FloatField = models.FloatField(null=True, blank=True)

    @classmethod
    def latest_versions(cls) -> models.QuerySet["Dataset"]:
        """Only the most recent version of each dataset (by zenodo_concept_id)."""
        latest_per_concept = (
            cls.objects.filter(zenodo_concept_id=OuterRef("zenodo_concept_id"))
            .order_by("-zenodo_record_id")
            .values("zenodo_record_id")[:1]
        )

        return cls.objects.filter(zenodo_record_id=Subquery(latest_per_concept))

    def __str__(self):
        return self.title


class DatasetProject(models.Model):
    """One project a dataset belongs to.

    project_ids is a list in the source JSON (a dataset can belong to
    multiple projects), so this is a separate table rather than a single
    FK on Dataset.
    """

    dataset: models.ForeignKey = models.ForeignKey(
        Dataset, on_delete=models.CASCADE, related_name="projects"
    )
    project_id: models.IntegerField = models.IntegerField()

    class Meta:
        constraints: ClassVar[list[models.UniqueConstraint]] = [
            models.UniqueConstraint(
                fields=["dataset", "project_id"], name="unique_dataset_project"
            )
        ]

    def __str__(self):
        return f"Project {self.project_id} ({self.dataset_id})"


class DatasetAuthors(models.Model):
    dataset: models.ForeignKey = models.ForeignKey(
        Dataset, on_delete=models.CASCADE, related_name="authors"
    )
    name: models.CharField = models.CharField(max_length=255)
    affiliation: models.CharField = models.CharField(max_length=500, null=True, blank=True)
    email: models.EmailField = models.EmailField(null=True, blank=True)
    orcid: models.CharField = models.CharField(max_length=50, null=True, blank=True)

    def __str__(self):
        return self.name


class DatasetFunders(models.Model):
    dataset: models.ForeignKey = models.ForeignKey(
        Dataset, on_delete=models.CASCADE, related_name="funders"
    )
    body: models.CharField = models.CharField(max_length=500)
    type: models.CharField = models.CharField(max_length=100, null=True, blank=True)
    ref: models.CharField = models.CharField(max_length=255, null=True, blank=True)
    url: models.URLField = models.URLField(null=True, blank=True)

    def __str__(self):
        return self.body


class DatasetPermits(models.Model):
    dataset: models.ForeignKey = models.ForeignKey(
        Dataset, on_delete=models.CASCADE, related_name="permits"
    )
    type: models.CharField = models.CharField(max_length=100)
    authority: models.CharField = models.CharField(max_length=500)
    number: models.CharField = models.CharField(max_length=255)

    def __str__(self):
        return f"{self.type} ({self.number})"


class DatasetKeywords(models.Model):
    dataset: models.ForeignKey = models.ForeignKey(
        Dataset, on_delete=models.CASCADE, related_name="keywords"
    )
    keyword: models.CharField = models.CharField(max_length=255)

    def __str__(self):
        return self.keyword


class DatasetWorksheets(models.Model):
    """One data worksheet within a dataset's Excel file.

    Deliberately excludes `descriptors` and `taxa_fields` from the source
    JSON: `descriptors` is parser bookkeeping about which metadata rows
    were present in the Excel sheet, not dataset content; `taxa_fields` is
    fully redundant with DatasetFields.field_type == "taxa" on individual
    fields.
    """

    dataset: models.ForeignKey = models.ForeignKey(
        Dataset, on_delete=models.CASCADE, related_name="worksheets"
    )
    name: models.CharField = models.CharField(max_length=255)
    title: models.CharField = models.CharField(max_length=500, null=True, blank=True)
    description: models.TextField = models.TextField(null=True, blank=True)

    max_row: models.IntegerField = models.IntegerField()
    max_col: models.IntegerField = models.IntegerField()
    field_name_row: models.IntegerField = models.IntegerField(null=True, blank=True)
    n_data_row: models.IntegerField = models.IntegerField(null=True, blank=True)

    # Unclear what this field should be:
    external: models.TextField = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"{self.name} ({self.dataset_id})"


class DatasetFields(models.Model):
    """Field-level metadata for one column within a dataset worksheet."""

    worksheet: models.ForeignKey = models.ForeignKey(
        DatasetWorksheets, on_delete=models.CASCADE, related_name="fields"
    )
    field_name: models.CharField = models.CharField(max_length=255)
    description: models.TextField = models.TextField(null=True, blank=True)
    field_type: models.CharField = models.CharField(max_length=50)
    units: models.CharField = models.CharField(max_length=255, null=True, blank=True)
    method: models.TextField = models.TextField(null=True, blank=True)

    # Unclear what these fields should be:
    levels: models.TextField = models.TextField(null=True, blank=True)
    range: models.TextField = models.TextField(null=True, blank=True)

    taxon_field: models.CharField = models.CharField(max_length=255, null=True, blank=True)
    taxon_name: models.CharField = models.CharField(max_length=255, null=True, blank=True)
    interaction_field: models.CharField = models.CharField(max_length=255, null=True, blank=True)
    interaction_name: models.CharField = models.CharField(max_length=255, null=True, blank=True)

    col_idx: models.IntegerField = models.IntegerField()

    def __str__(self):
        return self.field_name


class Taxa(models.Model):
    """One taxon referenced by a dataset.

    Unifies GBIF-sourced and sequence-sourced taxa into a single table. 
    taxon_id and parent_id are identifiers used only within this dataset's
    own taxon index.
    """

    SOURCE_GBIF = "gbif"
    SOURCE_SEQUENCE = "sequence"
    SOURCE_CHOICES: ClassVar[list[tuple[str, str]]] = [
        (SOURCE_GBIF, "GBIF"),
        (SOURCE_SEQUENCE, "Sequence"),
    ]

    dataset: models.ForeignKey = models.ForeignKey(Dataset, on_delete=models.CASCADE, related_name="taxa")
    source: models.CharField = models.CharField(max_length=20, choices=SOURCE_CHOICES)

    taxon_id: models.IntegerField = models.IntegerField()
    parent_id: models.IntegerField = models.IntegerField(null=True, blank=True)
    taxon_name: models.CharField = models.CharField(max_length=500)
    taxon_rank: models.CharField = models.CharField(max_length=100, null=True, blank=True)
    taxon_status: models.CharField = models.CharField(max_length=100, null=True, blank=True)
    worksheet_name: models.CharField = models.CharField(max_length=255, null=True, blank=True)

    # Only populated for source == "sequence". These are at the taxon-group level in the source JSON,
    # but duplicated per-row here for simplicity.
    database_name: models.CharField = models.CharField(max_length=255, null=True, blank=True)
    database_version: models.CharField = models.CharField(max_length=100, null=True, blank=True)
    database_link: models.URLField = models.URLField(null=True, blank=True)

    def __str__(self):
        return self.taxon_name


class Locations(models.Model):
    """A location used within a specific dataset.

    Usually points to an existing Gazetteer entry (gazetteer_location);
    can instead carry its own geometry for a new, one-off site not (yet)
    in the gazetteer.
    """

    dataset: models.ForeignKey = models.ForeignKey(
        Dataset, on_delete=models.CASCADE, related_name="locations"
    )
    name: models.CharField = models.CharField(max_length=255)
    new_location: models.BooleanField = models.BooleanField(default=False)

    gazetteer_location: models.ForeignKey = models.ForeignKey(
        "gazetteer.Gazetteer",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="dataset_usages",
    )
    geom_wgs84: gis_models.GeometryField = gis_models.GeometryField(srid=4326, null=True, blank=True)
    geom_local: gis_models.GeometryField = gis_models.GeometryField(
        srid=settings.GAZETTEER_LOCAL_EPSG, null=True, blank=True
    )

    def __str__(self):
        return f"{self.name} ({self.dataset_id})"


class DatasetFiles(models.Model):
    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE, related_name="files")
    filename = models.CharField(max_length=500)

    def __str__(self):
        return self.filename