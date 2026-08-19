"""Search API for the safedata package's data-discovery functions.
"""

from datetime import date

from datasets.models import Dataset, Taxa
from django.conf import settings
from django.contrib.gis.geos import GEOSGeometry
from django.db.models import Q, QuerySet
from gazetteer.models import Gazetteer
from rest_framework.response import Response
from rest_framework.views import APIView


class DatasetSearchError(Exception):
    """Raised when a search request has invalid or missing parameters."""


def _parse_ids(request) -> list[int]:
    """Parse the shared `ids` restriction parameter: zero or more
    zenodo_record_id values to restrict a search to."""
    raw_ids = request.GET.getlist("ids")
    if not raw_ids:
        return []

    try:
        return [int(value) for value in raw_ids]
    except ValueError as exc:
        raise DatasetSearchError(f"Invalid 'ids' parameter: {exc}") from exc


def _apply_common_filters(queryset: QuerySet, request) -> QuerySet:
    """Apply the two parameters every search endpoint shares: restrict to
    only the latest version of each dataset concept, and/or restrict to a
    specific set of prior result ids."""
    if "most_recent" in request.GET:
        latest_record_ids = Dataset.latest_versions().values_list(
            "zenodo_record_id", flat=True
        )
        queryset = queryset.filter(zenodo_record_id__in=latest_record_ids)

    ids = _parse_ids(request)
    if ids:
        queryset = queryset.filter(zenodo_record_id__in=ids)

    return queryset


def _serialize_results(queryset: QuerySet) -> dict:
    datasets = list(queryset.distinct())
    return {
        "count": len(datasets),
        "entries": [
            {
                "zenodo_record_id": dataset.zenodo_record_id,
                "zenodo_concept_id": dataset.zenodo_concept_id,
                "title": dataset.title,
                "access": dataset.access,
            }
            for dataset in datasets
        ],
    }


class DatasetSearchView(APIView):
    """Base class for a single search endpoint. Subclasses implement
    get_queryset() to build the search-specific filter; the base class
    handles applying the shared ids/most_recent restriction and
    formatting the response consistently across every endpoint."""

    def get(self, request, *args, **kwargs):
        try:
            queryset = self.get_queryset(request)
            queryset = _apply_common_filters(queryset, request)
        except DatasetSearchError as exc:
            return Response({"error": str(exc)}, status=400)

        return Response(_serialize_results(queryset))

    def get_queryset(self, request) -> QuerySet:
        raise NotImplementedError


class TextSearchView(DatasetSearchView):
    """Free text search across dataset title/description, worksheet
    titles, field descriptions, and keywords.

    GET /api/search/text/?text=forest
    """

    def get_queryset(self, request) -> QuerySet:
        text = request.GET.get("text")
        if not text:
            raise DatasetSearchError("Missing required 'text' parameter.")

        return Dataset.objects.filter(
            Q(title__icontains=text)
            | Q(description__icontains=text)
            | Q(keywords__keyword__icontains=text)
            | Q(worksheets__title__icontains=text)
            | Q(worksheets__fields__description__icontains=text)
        )


class AuthorSearchView(DatasetSearchView):
    """Search by dataset author name (full or partial match).

    GET /api/search/authors/?name=Ewers
    """

    def get_queryset(self, request) -> QuerySet:
        name = request.GET.get("name")
        if not name:
            raise DatasetSearchError("Missing required 'name' parameter.")

        return Dataset.objects.filter(authors__name__icontains=name)


class DateSearchView(DatasetSearchView):
    """Search by temporal extent, using the same three match semantics as
    the legacy safedata package: "intersect" (any overlap, default),
    "contain" (dataset's extent fully spans the given range), "within"
    (dataset's extent falls entirely inside the given range).

    GET /api/search/dates/?date=2014-06-12
    GET /api/search/dates/?date=2014-06-12,2015-06-11&match_type=contain
    """

    def get_queryset(self, request) -> QuerySet:
        date_param = request.GET.get("date")
        if not date_param:
            raise DatasetSearchError("Missing required 'date' parameter.")

        dates = [d.strip() for d in date_param.split(",") if d.strip()]
        if len(dates) not in (1, 2):
            raise DatasetSearchError("'date' must be one or two ISO dates.")

        try:
            parsed_dates = [date.fromisoformat(d) for d in dates]
        except ValueError as exc:
            raise DatasetSearchError(f"Invalid date in 'date': {exc}") from exc

        match_type = request.GET.get("match_type", "intersect")
        if match_type not in ("intersect", "contain", "within"):
            raise DatasetSearchError(
                "'match_type' must be one of: intersect, contain, within."
            )

        if len(parsed_dates) == 1:
            target = parsed_dates[0]
            # A single date: datasets whose extent covers that date.
            return Dataset.objects.filter(
                temporal_extent_start__lte=target, temporal_extent_end__gte=target
            )

        range_start, range_end = sorted(parsed_dates)

        if match_type == "contain":
            # Dataset's own extent must span the whole given range.
            return Dataset.objects.filter(
                temporal_extent_start__lte=range_start,
                temporal_extent_end__gte=range_end,
            )
        elif match_type == "within":
            # Dataset's own extent must fall entirely inside the given range.
            return Dataset.objects.filter(
                temporal_extent_start__gte=range_start,
                temporal_extent_end__lte=range_end,
            )
        else:  # intersect
            return Dataset.objects.filter(
                temporal_extent_start__lte=range_end,
                temporal_extent_end__gte=range_start,
            )


class FieldSearchView(DatasetSearchView):
    """Search data worksheet field metadata by text and/or field type.

    GET /api/search/fields/?text=temperature
    GET /api/search/fields/?field_type=numeric
    GET /api/search/fields/?text=temperature&field_type=numeric
    """

    def get_queryset(self, request) -> QuerySet:
        text = request.GET.get("text")
        field_type = request.GET.get("field_type")

        if not text and not field_type:
            raise DatasetSearchError(
                "At least one of 'text' or 'field_type' is required."
            )

        queryset = Dataset.objects.all()

        if text:
            queryset = queryset.filter(
                Q(worksheets__fields__field_name__icontains=text)
                | Q(worksheets__fields__description__icontains=text)
            )

        if field_type:
            queryset = queryset.filter(worksheets__fields__field_type=field_type)

        return queryset


class TaxaSearchView(DatasetSearchView):
    """Search by taxon name, rank, taxon id, or taxonomic source.

    GET /api/search/taxa/?name=Formicidae
    GET /api/search/taxa/?rank=family
    GET /api/search/taxa/?taxon_id=4342&source=gbif
    """

    def get_queryset(self, request) -> QuerySet:
        name = request.GET.get("name")
        rank = request.GET.get("rank")
        taxon_id = request.GET.get("taxon_id")
        source = request.GET.get("source")

        if not any([name, rank, taxon_id, source]):
            raise DatasetSearchError(
                "At least one of 'name', 'rank', 'taxon_id', or 'source' is required."
            )

        if source and source not in (Taxa.SOURCE_GBIF, Taxa.SOURCE_SEQUENCE):
            raise DatasetSearchError(
                f"'source' must be one of: {Taxa.SOURCE_GBIF}, {Taxa.SOURCE_SEQUENCE}."
            )

        queryset = Dataset.objects.all()

        if name:
            queryset = queryset.filter(taxa__taxon_name__icontains=name)
        if rank:
            queryset = queryset.filter(taxa__taxon_rank__iexact=rank)
        if taxon_id:
            try:
                taxon_id = int(taxon_id)
            except ValueError as exc:
                raise DatasetSearchError(f"Invalid 'taxon_id': {exc}") from exc
            queryset = queryset.filter(taxa__taxon_id=taxon_id)
        if source:
            queryset = queryset.filter(taxa__source=source)

        return queryset


class SpatialSearchView(DatasetSearchView):
    """Search by spatial overlap with a WKT geometry or a named gazetteer
    location, with an optional buffer distance in metres.

    Matches against a dataset's sampling locations - both those resolved
    to a known gazetteer entry (using its geom_local/geom_wgs84) and
    standalone new locations with their own recorded geometry (using
    Locations.geom_local/geom_wgs84). A dataset location with no geometry
    recorded at all (e.g. an unresolved new location with no wkt_wgs84)
    cannot match a spatial search, per the same behaviour as the legacy
    safedata package.

    Buffered (distance) searches reproject into the deployment's local
    projected CRS (settings.GAZETTEER_LOCAL_EPSG) before buffering, since
    accurate metre-based distances require a projected coordinate system
    rather than WGS84's angular degrees. Unbuffered searches compare
    directly in WGS84, which is topologically valid without needing a
    projected CRS.

    GET /api/search/spatial/?wkt=POINT(116.5 4.75)&distance=100000
    GET /api/search/spatial/?location=A_1&distance=2500
    GET /api/search/spatial/?wkt=POINT(116.5 4.75)
    """

    def get_queryset(self, request) -> QuerySet:
        wkt = request.GET.get("wkt")
        location_name = request.GET.get("location")
        distance = request.GET.get("distance")

        if bool(wkt) == bool(location_name):
            raise DatasetSearchError("Provide exactly one of 'wkt' or 'location'.")

        if wkt:
            try:
                query_geometry_wgs84 = GEOSGeometry(wkt, srid=4326)
            except Exception as exc:
                raise DatasetSearchError(f"Invalid 'wkt': {exc}") from exc
        else:
            try:
                gazetteer_entry = Gazetteer.objects.get(location=location_name)
            except Gazetteer.DoesNotExist as exc:
                raise DatasetSearchError(
                    f"Location {location_name!r} not found in gazetteer."
                ) from exc
            query_geometry_wgs84 = gazetteer_entry.geom_wgs84

        if distance:
            try:
                distance = float(distance)
            except ValueError as exc:
                raise DatasetSearchError(f"Invalid 'distance': {exc}") from exc

            query_geometry_local = query_geometry_wgs84.transform(
                settings.GAZETTEER_LOCAL_EPSG, clone=True
            ).buffer(distance)

            return Dataset.objects.filter(
                locations__gazetteer_location__geom_local__intersects=query_geometry_local
            )

        return Dataset.objects.filter(
            Q(locations__gazetteer_location__geom_wgs84__intersects=query_geometry_wgs84)
            | Q(
                locations__gazetteer_location__isnull=True,
                locations__geom_wgs84__intersects=query_geometry_wgs84,
            )
        )