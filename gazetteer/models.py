"""Gazetteer database setup."""

from typing import ClassVar

from django.conf import settings
from django.contrib.gis.db import models
from django.core.exceptions import ValidationError
from django.db.models import Q


class Gazetteer(models.Model):
    """The set of recognised sampling locations for the project.
    
    Each location has a name and a geometry, stored in both WGS84 (global
    lat/lon) and a local projected coordinate system (for accurate distance
    and area calculations). The local coordinate system is project specific
    and is set via the GAZETTEER_LOCAL_EPSG environment variable.
    """

    location: models.CharField = models.CharField(max_length=255, unique=True)
    geom_wgs84: models.GeometryField = models.GeometryField(srid=4326)
    geom_local: models.GeometryField = models.GeometryField(
        srid=settings.GAZETTEER_LOCAL_EPSG
    )

    def __str__(self):
        return self.location


class GazetteerAlias(models.Model):
    """Alias names for gazetteer locations.

    Allows a name used in a dataset (which doesn't match an official
    gazetteer location) to be mapped onto one retrospectively. The dataset
    attribute means that the same alias could be used in different datasets
    without confusion. If `dataset` is null, the alias is a general alias 
    that applies across all datasets; otherwise it only applies within that
    specific dataset.
    """

    dataset: models.ForeignKey = models.ForeignKey(
        "datasets.Dataset",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="location_aliases",
    )
    location: models.ForeignKey = models.ForeignKey(
        Gazetteer,
        on_delete=models.CASCADE,
        related_name="aliases",
    )
    alias: models.CharField = models.CharField(max_length=255)

    class Meta:
        constraints: ClassVar[list[models.UniqueConstraint]] = [
            # General aliases (dataset is null) must be unique on their own.
            models.UniqueConstraint(
                fields=["alias"],
                condition=Q(dataset__isnull=True),
                name="unique_general_alias",
            ),
            # Per-dataset aliases only need to be unique within that dataset.
            models.UniqueConstraint(
                fields=["dataset", "alias"],
                condition=Q(dataset__isnull=False),
                name="unique_dataset_alias",
            ),
        ]

    def clean(self):
        # An alias cannot duplicate an existing official gazetteer location
        # name.
        if Gazetteer.objects.filter(location=self.alias).exists():
            raise ValidationError(
                {"alias": "This name is already a gazetteer location."}
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.alias} → {self.location.location} ({self.dataset_id or "general"})"