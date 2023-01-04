from csv import DictReader
from io import StringIO
import os
import datetime
import hashlib
import json

from shapely.geometry import box, shape

# The web2py HTML helpers are provided by gluon. This also provides the 'current'
# object, which provides the web2py 'request' API (note the single letter difference
# from the requests package!). The 'current' object is also extended by models/db.py to
# include the current 'db' DAL object and the 'myconf' AppConfig object so that they can
# accessed by this module

from gluon import current
from gluon.serializers import json as web2py_json


def get_index():

    """
    Function to generate a JSON string containing the formatted contents of the dataset
    files table. This is used as the core index of the safedata package, so is cached in
    a file like format along with MD5 hashes of the index and other files to speed up
    checking for updates and refreshing the index.
    """

    # version of the data contained in the dataset description
    db = current.db
    val = (
        db(db.published_datasets.id == db.dataset_files.dataset_id)
        .select(
            db.published_datasets.publication_date,
            db.published_datasets.zenodo_concept_id,
            db.published_datasets.zenodo_record_id,
            db.published_datasets.dataset_access,
            db.published_datasets.dataset_embargo,
            db.published_datasets.dataset_title,
            db.published_datasets.most_recent,
            db.dataset_files.checksum,
            db.dataset_files.filename,
            db.dataset_files.filesize,
            orderby=[db.published_datasets.id, db.dataset_files.id],
        )
        .as_list()
    )

    # repackage the db output into a single dictionary per file
    [r["published_datasets"].update(r.pop("dataset_files")) for r in val]
    val = [r["published_datasets"] for r in val]

    # Find the hashes
    index_hash = hashlib.md5(web2py_json(val).encode("utf-8")).hexdigest()

    # Use the file hash of the static gazetteer geojson
    gazetteer_file = os.path.join(
        current.request.folder, "static", "files", "gis", "gazetteer.geojson"
    )
    with open(gazetteer_file) as f:
        gazetteer_hash = hashlib.md5(f.read().encode("utf-8")).hexdigest()

    # Use the file hash of the static locations alias csv
    location_aliases_file = os.path.join(
        current.request.folder, "static", "files", "gis", "location_aliases.csv"
    )
    with open(location_aliases_file) as f:
        location_aliases_hash = hashlib.md5(f.read().encode("utf-8")).hexdigest()

    return dict(
        hashes=dict(
            index=index_hash,
            gazetteer=gazetteer_hash,
            location_aliases=location_aliases_hash,
        ),
        index=val,
    )


def server_post_metadata(payload: dict) -> int:
    """Populate the dataset tables from posted metadata.

    This function takes a dictionary payload from the JSON request body containing both
    the Zenodo metadata for a published dataset and the dataset validation metadata from
    safedata_validator. It then uses this payload to populate the various dataset
    tables.

    Args:
        payload: The parsed JSON payload

    Returns:
        The integer ID of the resulting row in published_datasets.
    """

    db = current.db
    dataset = payload["metadata"]
    zenodo = payload["zenodo"]

    # Now create a published datasets entry
    published_record = db.published_datasets.insert(
        upload_datetime=datetime.datetime.now(),
        # submission_id=record.id,
        dataset_title=dataset["title"],
        dataset_access=dataset["access"],
        dataset_embargo=dataset["embargo_date"],
        dataset_conditions=dataset["access_conditions"],
        dataset_description=dataset["description"],
        dataset_metadata=dataset,
        temporal_extent_start=dataset["temporal_extent"][0],
        temporal_extent_end=dataset["temporal_extent"][1],
        geographic_extent=box(
            dataset["longitudinal_extent"][0],
            dataset["latitudinal_extent"][0],
            dataset["longitudinal_extent"][1],
            dataset["latitudinal_extent"][1],
        ).wkt,
        publication_date=zenodo["metadata"]["publication_date"],
        most_recent=True,
        zenodo_record_id=zenodo["record_id"],
        zenodo_record_doi=zenodo["doi_url"],
        zenodo_record_badge=zenodo["links"]["badge"],
        zenodo_concept_id=zenodo["conceptrecid"],
        zenodo_concept_doi=zenodo["links"]["conceptdoi"],
        zenodo_concept_badge=zenodo["links"]["conceptbadge"],
        zenodo_metadata=zenodo,
    )

    # update to include the local geometry
    db(db.published_datasets.id == published_record).update(
        geographic_extent_local=db.published_datasets.geographic_extent.st_transform(
            current.configuration.get("geo.local_epsg")
        )
    )

    # populate index tables
    # A) Taxa
    taxa = dataset["gbif_taxa"]
    [tx.update({"dataset_id": published_record, "taxon_auth": "GBIF"}) for tx in taxa]
    db.dataset_taxa.bulk_insert(taxa)

    taxa = dataset["ncbi_taxa"]
    [tx.update({"dataset_id": published_record, "taxon_auth": "NCBI"}) for tx in taxa]
    db.dataset_taxa.bulk_insert(taxa)

    # B) Files, using the Zenodo response
    files = zenodo["files"]
    for each_file in files:
        each_file["dataset_id"] = published_record
        each_file["download_link"] = each_file["links"]["download"]
        each_file["file_zenodo_id"] = each_file.pop("id")

    db.dataset_files.bulk_insert(files)

    # C) Locations
    locations = dataset["locations"]
    [lc.update({"dataset_id": published_record}) for lc in locations]

    new_locs = db.dataset_locations.bulk_insert(locations)

    # update the UTM 50 N geometry where possible
    db(db.dataset_locations.id.belongs(new_locs)).update(
        wkt_local=db.dataset_locations.wkt_wgs84.st_transform(32650)
    )

    # D) Dataworksheets and fields
    for data in dataset["dataworksheets"]:

        worksheet_id = db.dataset_worksheets.insert(dataset_id=published_record, **data)

        for fld in data["fields"]:
            fld["dataset_id"] = published_record
            fld["worksheet_id"] = worksheet_id

        db.dataset_fields.bulk_insert(data["fields"])

    # E) Authors
    for auth in dataset["authors"]:
        db.dataset_authors.insert(dataset_id=published_record, **auth)

    # F) Funders
    if dataset["funders"] is not None:
        for fndr in dataset["funders"]:
            db.dataset_funders.insert(dataset_id=published_record, **fndr)

    # G) Permits
    if dataset["permits"] is not None:
        for perm in dataset["permits"]:
            db.dataset_permits.insert(dataset_id=published_record, **perm)

    # K) Keywords
    if dataset["keywords"] is not None:
        for kywd in dataset["keywords"]:
            db.dataset_keywords.insert(dataset_id=published_record, keyword=kywd)

    # Update the index
    current.cache.ram.clear("index")
    current.cache.ram("index", get_index, None)

    return published_record


def server_update_gazetteer(payload: dict) -> None:
    """Update the gazetteer data used by the server

    This function takes a dictionary payload from the JSON request body containing both
    the gazetteer GeoJSON data and the location aliases data. It then uses this data to
    update the local static copies of those files and the database.

    This controller reloads the contents of the gazetteer table and the alias table from
    the files provided and then updates the local geometry field. Note that this relies
    on web2py 2.18.5+, which includes a version of PyDAL that supports st_transform.

    The files uploaded here are versioned to serve updated details via the API and so
    this function also clears the file hashes from the RAM cache, so that the next
    request for the index hashes will repopulate them.

    Args:
        payload: The parsed JSON payload
    """

    gazetteer = payload["gazetteer"]
    location_aliases = payload["location_aliases"]

    # Update gazetteer table
    db = current.db

    try:
        # drop the current contents
        db.gazetteer.truncate()

        # Loop over the features, inserting the properties and using shapely to convert
        # the geojson geometry to WKT, prepending the PostGIS extended WKT statement of
        # the EPSG code for the geometry
        for ft in gazetteer["features"]:
            data = ft["properties"]
            data["wkt_wgs84"] = "SRID=4326;" + shape(ft["geometry"]).wkt
            db.gazetteer.insert(**data)

        # Recalculate the local projected geometries - using the extended pydal GIS
        db(db.gazetteer).update(
            wkt_local=db.gazetteer.wkt_wgs84.st_transform(
                current.configuration.get("geo.local_epsg")
            )
        )
    except:
        db.rollback()
        raise ValueError("Could not load gazetteer data")

    # Update GAZETTEER ALIASES
    try:
        #  - drop the current contents
        db.gazetteer_alias.truncate()
        print(location_aliases)
        # Parse the data into row dictionaries and set NA values to None
        data = list(DictReader(StringIO(location_aliases)))
        for row in data:
            if row["zenodo_record_id"] == "NA":
                row["zenodo_record_id"] = None
            # Insert the data rows
            db.gazetteer_alias.insert(**row)
    except:
        db.rollback()
        raise ValueError("Could not load location alias data")

    # Write the files to static
    gaz_dir = os.path.join(current.request.folder, "static", "files", "gis")
    os.makedirs(gaz_dir, exist_ok=True)

    gaz_file = os.path.join(gaz_dir, "gazetteer.geojson")
    with open(gaz_file, "w") as gaz_out:
        json.dump(obj=gazetteer, fp=gaz_out)

    alias_file = os.path.join(gaz_dir, "location_aliases.csv")
    with open(alias_file, "w") as alias_out:
        alias_out.write(location_aliases)

    # Update the index cache
    current.cache.ram.clear("index")
    current.cache.ram("index", get_index, None)

    # Now if all is well, allow those updates to be committed.
    db.commit()

    return


# API search functions


def dataset_query_to_json(
    qry,
    most_recent=False,
    ids=None,
    fields=[
        ("published_datasets", "zenodo_concept_id"),
        ("published_datasets", "zenodo_record_id"),
        ("published_datasets", "dataset_title"),
    ],
):
    """
    Shared function to take a Query including rows in db.published datasets
    and return a standardised set of attributes and a count.
    """

    db = current.db

    if most_recent:
        qry &= db.published_datasets.most_recent == True

    if ids is not None:
        qry &= db.published_datasets.zenodo_record_id.belongs(ids)

    # Turn fields argument into fields references and select
    fields = [db[t][f] for t, f in fields]
    rows = db(qry).select(*fields, distinct=True)

    return {"count": len(rows), "entries": rows}


def dataset_taxon_search(gbif_id=None, name=None, rank=None):

    """Search for datasets by taxon information

    Examples:
        /api/search/taxa?name=Formicidae
        /api/search/taxa?gbif_id=4342
        /api/search/taxa?rank=Family

    Args:
        gbif_id (int): A GBIF taxon id.
        name (str): A scientific name
        rank (str): A taxonomic rank. Note that GBIF only provides
            kingdom, phylum, order, class, family, genus and species.
    """

    db = current.db
    qry = db.published_datasets.id == db.dataset_taxa.dataset_id

    if gbif_id is not None:
        qry &= db.dataset_taxa.gbif_id == gbif_id

    if name is not None:
        qry &= db.dataset_taxa.taxon_name == name

    if rank is not None:
        qry &= db.dataset_taxa.taxon_rank == rank.lower()

    return qry


def dataset_author_search(name=None):

    """Search for datasets by author name

    Examples:
        /api/search/authors?name=Wilk

    Args:
        name (str): An author name or part of a name
    """

    db = current.db
    qry = db.published_datasets.id == db.dataset_authors.dataset_id

    if name is not None:
        qry &= db.dataset_authors.name.contains(name.lower())

    return qry


def dataset_locations_search(name=None):

    """Search for datasets with data at a named location

    Examples:
        /api/search/location?name=A_1

    Args:
        name (str): A location name
    """

    db = current.db
    qry = db.published_datasets.id == db.dataset_locations.dataset_id

    if name is not None:
        qry &= db.dataset_locations.name.contains(name.lower())

    return qry


def dataset_date_search(date=None, match_type="intersect"):

    """Search for datasets by temporal extent

    Examples:
        /api/search/dates?date=2014-06-12
        /api/search/dates?date=2014-06-12,2015-06-12
        /api/search/dates?date=2014-06-12,2015-06-12&match_type=contains
        /api/search/dates?date=2014-06-12,2015-06-12&match_type=within

    Args:
        date (str): A string containing one or two (comma separated) dates in ISO format (2019-06-12)
        match_type (str): One of 'intersect', 'contain' and 'within' to match the provided dates to
            the temporal extents of datasets. The 'contain' option returns datasets that span a date
            range and 'within' returns datasets that fall within that date range.
    """

    db = current.db

    # parse the data query: can be a single iso date or a comma separated pair.
    try:
        date_vals = date.split(",")
        date_vals = [
            datetime.datetime.strptime(dt, "%Y-%m-%d").date() for dt in date_vals
        ]
    except ValueError:
        return {"error": 400, "message": "Could not parse dates: {}".format(date)}

    # Check the number of dates and enforce order
    if len(date_vals) > 2:
        return {
            "error": 400,
            "message": "date contains more than two values: {}".format(date),
        }
    elif len(date_vals) == 2:
        date_vals.sort()
    else:
        # make singular dates a 'range' to use same predicate mechanisms
        date_vals += date_vals

    # check the dates against the temporal extents of the datasets
    if match_type == "intersect":
        qry = ~(
            (db.published_datasets.temporal_extent_start >= date_vals[1])
            | (db.published_datasets.temporal_extent_end <= date_vals[0])
        )
    elif match_type == "contain":
        qry = (db.published_datasets.temporal_extent_start >= date_vals[0]) & (
            db.published_datasets.temporal_extent_end <= date_vals[1]
        )
    elif match_type == "within":
        qry = (db.published_datasets.temporal_extent_start <= date_vals[0]) & (
            db.published_datasets.temporal_extent_end >= date_vals[1]
        )
    else:
        return {
            "error": 400,
            "message": "Unknown date match type: {}".format(match_type),
        }

    return qry


def dataset_field_search(text=None, ftype=None):

    """Search for datasets by data field information

    Examples:
        /api/search/fields?text=temperature
        /api/search/fields?ftype=numeric
        /api/search/fields?text=temperature&ftype=numeric

    Args:
        text (str): A string to look for within the field name and description.
        ftype (str): A field type to match.
    """

    db = current.db
    qry = db.published_datasets.id == db.dataset_fields.dataset_id

    if text is not None:
        qry &= (db.dataset_fields.field_name.contains(text)) | (
            db.dataset_fields.description.contains(text)
        )

    if ftype is not None:
        qry &= db.dataset_fields.field_type.ilike(ftype)

    return qry


def dataset_text_search(text=None):

    """Search for datasets by free text search

    Examples:
        /api/search/text?text=humus

    Args:
        text (str): A string to look within dataset, worksheet and field
        descriptions and titles and in dataset keywords.
    """

    db = current.db

    qry = (
        (db.published_datasets.id == db.dataset_fields.dataset_id)
        & (db.published_datasets.id == db.dataset_worksheets.dataset_id)
        & (db.published_datasets.id == db.dataset_keywords.dataset_id)
        & (
            (db.dataset_fields.field_name.contains(text))
            | (db.dataset_fields.description.contains(text))
            | (db.dataset_worksheets.title.contains(text))
            | (db.dataset_worksheets.description.contains(text))
            | (db.published_datasets.dataset_title.contains(text))
            | (db.published_datasets.dataset_description.contains(text))
            | (db.dataset_keywords.keyword.contains(text))
        )
    )

    return qry


def dataset_parse_spatial(wkt=None, location=None):

    """
    Shared function to parse query geometry options - either a location or a WKT - and get
    # the query geometry as a UTM 50N geometry.
    """
    db = current.db

    if (location is not None) and (wkt is not None):
        return {
            "error": 400,
            "message": "Provide a location name or a WKT geometry, not both",
        }
    elif location is None and wkt is None:
        return {
            "error": 400,
            "message": "Provide either a location name or a WKT geometry",
        }
    elif location is not None:
        gazetteer_location = gazetteer_location = (
            db(db.gazetteer.location == location)
            .select(db.gazetteer.wkt_local.st_aswkb().with_alias("wkb"))
            .first()
        )
        if gazetteer_location is not None:
            query_geom = gazetteer_location.wkb
        else:
            return {"error": 400, "message": "Unknown location"}
    elif wkt is not None:
        # Validate the geometry - there isn't currently a validator, so use the DB (?shapely)
        # i) Does the WKT parse correctly to a WKB string, assuming WGS84 for now
        try:
            query_geom = db.executesql(
                "select st_geomfromtext('{}', 4326);".format(wkt)
            )[0][0]
        except (db._adapter.driver.ProgrammingError, db._adapter.driver.InternalError):
            return {"error": 400, "message": "Could not parse WKT geometry"}

        # ii) Do the coordinates seem like lat long?
        is_lat_long = db.executesql(
            "SELECT ST_XMin(g) >= -180 AND ST_XMax(g) <= 180 AND "
            "   ST_YMin(g) >= -90 AND ST_YMax(g) <= 90 "
            "   FROM (SELECT st_geomfromwkb(decode('{0}', 'hex')) "
            "AS g) AS sel ;".format(query_geom)
        )[0][0]
        if not is_lat_long:
            return {"error": 400, "message": "WKT geometry coordinates not as lat/long"}

        # iii) Convert to local projected
        query_geom = db.executesql(
            "SELECT st_transform(st_geomfromwkb(decode('{0}', 'hex')), {1});".format(
                query_geom, current.configuration.get("geo.local_epsg")
            )
        )[0][0]

    return query_geom


def dataset_spatial_search(wkt=None, location=None, distance=0):

    """Spatial search for sampling locations.

    This endpoint can search for datasets using either a user-provided geometry or the geometry
    of a named location from the SAFE gazetteer. The sampling locations provided in each dataset
    are tested to see if they intersect the search geometry and a buffer distance can also be
    provided to search around the query geometry.

    Note that this endpoint will not retrieve datasets that have not provided sampling locations
    or use new locations that are missing coordinate information. The bounding box endpoint
    uses the dataset geographic extent, which is provided for all datasets.

    Examples:
        /api/search/spatial?location=A_1
        /api/search/spatial?location=A_1&distance=50
        /api/search/spatial?wkt=Point(116.5 4.75)
        /api/search/spatial?wkt=Point(116.5 4.75)&distance=50000
        /api/search/spatial?wkt=Polygon((110 0, 110 10,120 10,120 0,110 0))

    Args:
        wkt (str): A well-known text geometry. This is assumed to use latitude and longitude
            coordinates in WGS84 (EPSG:4326).
        location (str): A location name used to select a query geometry from the SAFE gazetteer.
        distance (float): A search distance in metres. All geometries are converted to the
            UTM 50N projection to provide appopriate distance searching.
    """

    db = current.db

    # validate the query geometry options and report back if there is an error
    query_geom = dataset_parse_spatial(wkt, location)
    if isinstance(query_geom, dict):
        return query_geom

    qry = (
        (db.published_datasets.id == db.dataset_locations.dataset_id)
        & (db.dataset_locations.name == db.gazetteer.location)
        & (
            (db.gazetteer.wkt_local.st_distance(query_geom) <= distance)
            | (db.dataset_locations.wkt_local.st_distance(query_geom) <= distance)
        )
    )

    return qry


def dataset_spatial_bbox_search(
    wkt=None, location=None, match_type="intersect", distance=None
):

    """Spatial search for dataset bounding boxes

    The endpoint can search for datasets using either a user-provided geometry or a location
    name from the SAFE gazetteer. This endpoint uses only the dataset bounding box, which is
    provided for all datasets, rather than sampling location information which may not be
    recorded for some datasets.

    Examples:
        /api/search/bbox?wkt=Polygon((110 0, 110 10,120 10,120 0,110 0))
        /api/search/bbox?wkt=Polygon((116 4.5,116 5,117 5,117 4.5,116 4.5))
        /api/search/bbox?wkt=Polygon((116 4.5,116 5,117 5,117 4.5,116 4.5))&match_type=contain
        /api/search/bbox?wkt=Point(116.5 4.75)&match_type=within

    Args:
        wkt (str): A well-known text geometry. This is assumed to use latitude and longitude
            coordinates in WGS84 (EPSG:4326).
        location (str): A location name used to select a query geometry from the SAFE gazetteer.
        match_type (str): One of 'intersect', 'contain' and 'within' to match the provided geometry
            to the geographic extents of datasets. The 'contain' option returns datasets that
            completely cover the query geometry and 'within' returns datasets that fall entirely
            within the query geometry.

    """

    db = current.db

    # validate the query geometry options and report back if there is an error
    query_geom = dataset_parse_spatial(wkt, location)
    if isinstance(query_geom, dict):
        return query_geom

    # validate the match type
    if match_type not in ["intersect", "contain", "within", "distance"]:
        return {
            "error": 400,
            "message": "Unknown spatial match type: {}".format(match_type),
        }

    # Query the geographic extents with the appropriate predicate
    if match_type == "intersect":
        qry = db.published_datasets.geographic_extent_local.st_intersects(query_geom)
    elif match_type == "contain":
        qry = db.published_datasets.geographic_extent_local.st_contains(query_geom)
    elif match_type == "within":
        qry = db.published_datasets.geographic_extent_local.st_within(query_geom)
    elif match_type == "distance":
        qry = (
            db.published_datasets.geographic_extent_local.st_distance(query_geom)
            <= distance
        )

    return qry
