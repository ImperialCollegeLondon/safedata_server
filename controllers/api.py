# -*- coding: utf-8 -*-

"""The safedata_server API.

This controller defines the safedata_server API endpoints, which are used to:

* interact with administrators posting new dataset metadata or gazetteer data from the
  safedata_validator package, and
* interact with users requesting dataset metadata, via the safedata R package.

Individual API endpoints are exposed using the web2py @request.restful decorator.
"""

import os
import sys
import traceback
import inspect
import json

from gluon.serializers import json as web2py_json

from safedata_server_api import (
    dataset_taxon_search,
    dataset_author_search,
    dataset_date_search,
    dataset_text_search,
    dataset_field_search,
    dataset_locations_search,
    dataset_spatial_search,
    dataset_spatial_bbox_search,
    dataset_query_to_json,
    get_index,
    server_post_metadata,
    server_update_gazetteer,
)


# A list of endpoint names to document in help
API_ENDPOINTS = [
    "post_metadata",
    "update_gazetteer",
    "gazetteer",
    "location_aliases",
    "metadata_index",
    "metadata_index_hashes",
    "records",
    "files",
    "taxa",
    "search",
]

# A dictionary of search endpoint names and the underlying functions.
SEARCH_FUNC = {
    "taxa": dataset_taxon_search,
    "authors": dataset_author_search,
    "dates": dataset_date_search,
    "text": dataset_text_search,
    "fields": dataset_field_search,
    "locations": dataset_locations_search,
    "spatial": dataset_spatial_search,
    "bbox": dataset_spatial_bbox_search,
}


# ------------------------------------------------------------------
# Website dataset API index page
# ------------------------------------------------------------------


def index():
    """Help page for the dataset server API

    This controller serves help documentation about the API to the root URL of the API
    endpoint.
    """

    # API endpoint documentation from their docstrings
    docs = TABLE(
        [
            (TAG.CODE(endpt), PRE(inspect.getdoc(globals()[endpt])))
            for endpt in API_ENDPOINTS
        ],
        _class="table table-striped",
    )

    # Search function docstrings as HTML
    srch_docs = TABLE(
        [(TAG.CODE(ky), PRE(inspect.getdoc(fn))) for ky, fn in SEARCH_FUNC.items()],
        _class="table table-striped",
    )

    return dict(docs=docs, srch_docs=srch_docs)


# ------------------------------------------------------------------
# API Resources
# ------------------------------------------------------------------


def _parse_vars(vars):
    if "most_recent" in vars:
        most_recent = vars.pop("most_recent")

        if most_recent == "":
            most_recent = True
        else:
            raise HTTP(400, "Do not provide a value for the most_recent query flag.")
    else:
        most_recent = False

    if "ids" in vars:
        ids = vars.pop("ids")

        if isinstance(ids, str):
            ids = [ids]

        try:
            ids = [int(vl) for vl in ids]
        except ValueError:
            raise HTTP(400, "Invalid ids value")

    else:
        ids = None

    return most_recent, ids


@request.restful()
def gazetteer():
    """Returns the content of the gazetteer GeoJSON file.

    Example use:
        /api/gazetteer.json
    """

    response.view = "generic.json"

    def GET(*args, **vars):
        try:
            fpath = os.path.join(request.folder, "static/files/gis/gazetteer.geojson")
            with open(fpath, "rb") as fdata:
                return fdata.read()
        except FileNotFoundError as err:
            raise HTTP(400, "Gazetteer data not loaded")

    return locals()


@request.restful()
def location_aliases():
    """Returns the content of the location aliases CSV file.

    Example use:
        /api/location_aliases.csv
    """

    response.view = "generic.json"

    def GET(*args, **vars):
        try:
            fpath = os.path.join(
                request.folder, "static/files/gis/location_aliases.csv"
            )
            with open(fpath, "rb") as fdata:
                return fdata.read()
        except FileNotFoundError as err:
            raise HTTP(400, "Gazetteer data not loaded")

    return locals()


@request.restful()
def metadata_index_hashes():
    """Get the MD5 hashes for the metadata index, gazetteer and location aliases.

    Example use:
        /api/metadata_index_hashes.json
    """

    response.view = "generic.json"
    request.env.content_type = request.env.content_type or "application/json"

    def GET(*args, **vars):
        return cache.ram("index", get_index, time_expire=None)["hashes"]

    return locals()


@request.restful()
def metadata_index():
    """Get the complete dataset metadata index

    Example use:
        /api/metadata_index.json
    """

    # The output from this endpoint is used as the core index for the safedata
    # R package. The output is therefore cached in ram: i) to speed up access and
    # ii) to provide an MD5 hash of the contents to provide a version stamp. Note
    # the expiry date of None in the cache means that it never expires - publishing
    # a new dataset therefore needs to clear the ram cache to reset these version
    # stamps

    response.view = "generic.json"

    def GET(*args, **vars):
        val = cache.ram("index", get_index, time_expire=None)["index"]
        return web2py_json(val)

    return locals()


@request.restful()
def post_metadata():
    """Post dataset and zenodo metadata for a validated and published dataset.

    The post request body should be JSON data providing two metadata objects: "dataset"
    for the dataset metadata and "zenodo" for the Zenodo publication metadata, and the
    request must include the variable 'token', providing a valid security token.
    """
    response.view = "generic.json"

    def POST(*args, **vars):
        # Check the validation token
        if configuration.get("metadata_upload.token") != vars.get("token"):
            raise HTTP(403, "Invalid metadata upload token.")

        try:
            payload = json.load(request.body)
        except Exception as err:
            raise HTTP(400, "Malformed JSON payload")

        try:
            val = server_post_metadata(payload)
        except Exception as err:
            raise HTTP(400, str(err))

        # Update the response status code for POST action and return inserted entry
        response.status = 201
        return val

    return locals()


@request.restful()
def update_gazetteer():
    """Update the gazeetteer and location aliases data.

    The post request body should be JSON data providing two objects: "gazetteer" JSON
    data and the "location_aliases" file data as a CSV string. The request must also
    include the variable 'token', providing a valid security token.
    """

    response.view = "generic.json"

    def POST(*args, **vars):
        # Check the validation token
        if configuration.get("metadata_upload.token") != vars.get("token"):
            raise HTTP(403, "Invalid metadata upload token.")

        try:
            payload = json.load(request.body)
        except Exception as err:
            raise HTTP(400, "Malformed JSON payload")

        try:
            val = server_update_gazetteer(payload)
        except Exception as err:
            raise HTTP(400, str(err))

        # Update the response status code for POST action and return inserted entry
        response.status = 201
        return True

    return locals()


@request.restful()
def record():
    """Get JSON metadata for a single dataset record.

    This endpoint returns the metadata for a single provided Zenodo record ID. This is
    exactly the same information used to populate the dataset description on the Zenodo
    dataset page but as machine readable JSON data.

    Example usage:
        /api/record/1198302.json
    """
    response.view = "generic.json"

    def GET(*args, **vars):
        if len(request.args) == 1:
            try:
                record_id = int(request.args[0])
            except ValueError:
                raise HTTP(400, "Non-integer record number")
            else:
                record = (
                    db(db.published_datasets.zenodo_record_id == record_id)
                    .select()
                    .first()
                )

                if record is None:
                    raise HTTP(404, "Unknown record number.")
                else:
                    # Build the record metadata, including taxa and locations
                    val = record.dataset_metadata
                    val["publication_date"] = record.publication_date
                    val["zenodo_concept_id"] = record.zenodo_concept_id
                    val["zenodo_record_id"] = record.zenodo_record_id
                    # TODO: Decide here!
                    # val["taxa"] = record.dataset_taxa.select()
                    # val["locations"] = record.dataset_locations.select(
                    #     db.dataset_locations.name,
                    #     db.dataset_locations.new_location,
                    #     db.dataset_locations.wkt_wgs84,
                    # )

                    return val

        raise HTTP(400, "Bad request: records endpoint requires one integer argument")

    return locals()


@request.restful()
def files():
    """Get the files associated with datasets.

    Datasets have associated datafiles, often a single Excel file, but possibly also
    including external data files. The response includes a count of returned files and
    then a JSON array of file details, including a download link for the file. The
    download link is only functional when a dataset is open access or if the listed
    embargo date has passed.

    This endpoint does accept the shared <code>ids</code> or <code>most_recent</code>
    query parameters.

    Example usage:
        /api/files.json
        /api/files.json?most_recent
    """
    response.view = "generic.json"

    def GET(*args, **vars):
        most_recent, ids = _parse_vars(vars)

        # /api/files endpoint provides a json file containing the files associated
        # with dataset records, allowing filtering by ID and most_recent query parameters

        # version of the data contained in the dataset description
        qry = db.published_datasets.id == db.dataset_files.dataset_id
        val = dataset_query_to_json(
            qry,
            most_recent,
            ids,
            fields=[
                ("published_datasets", "publication_date"),
                ("published_datasets", "zenodo_concept_id"),
                ("published_datasets", "zenodo_record_id"),
                ("published_datasets", "dataset_access"),
                ("published_datasets", "dataset_embargo"),
                ("published_datasets", "dataset_title"),
                ("published_datasets", "most_recent"),
                ("dataset_files", "checksum"),
                ("dataset_files", "filename"),
                ("dataset_files", "filesize"),
            ],
        )

        # repackage the db output into a single dictionary per file
        entries = val["entries"].as_list()
        [r["published_datasets"].update(r.pop("dataset_files")) for r in entries]
        val["entries"] = [r["published_datasets"] for r in entries]

        return val

    return locals()


@request.restful()
def taxa():
    """Get JSON data on the taxon names currently used in datasets.

    The response is a list of taxon details, including a count of the number of datasets
    recording each taxon.

    Example use:
        /api/taxa.json
    """
    response.view = "generic.json"

    def GET(*args, **vars):
        taxon_fields = [
            db.dataset_taxa.taxon_auth,
            db.dataset_taxa.taxon_id,
            db.dataset_taxa.taxon_rank,
            db.dataset_taxa.taxon_name,
            db.dataset_taxa.taxon_status,
            db.dataset_taxa.parent_id,
        ]

        taxon_count = [db.dataset_taxa.taxon_name.count().with_alias("n_datasets")]

        val = (
            db(db.dataset_taxa)
            .select(*taxon_fields + taxon_count, groupby=taxon_fields)
            .as_list()
        )

        # repackage the Rows to provide a flat json per taxon format.
        for txn in val:
            txn.update(txn.pop("dataset_taxa"))
            del txn["_extra"]

        return web2py_json(val)

    return locals()


@request.restful()
def search():
    """Search for datasets

    This endpoint provides a number of search options used to identify datasets that
    meet different search criteria. See the search function documentation below for the
    different search arguments and query variables.
    """
    response.view = "generic.json"

    def GET(*args, **vars):
        if len(args) == 1 and args[0] in SEARCH_FUNC:
            # validate the remaining query search parameters to the search function
            # arguments
            func = SEARCH_FUNC[args[0]]
            fn_args = inspect.getargspec(func).args
            unknown_args = set(vars) - set(fn_args)

            if unknown_args:
                unknown_args = ",".join(unknown_args)
                raise HTTP(
                    400, f"Unknown variables for search/{args[0]}: {unknown_args}"
                )
            else:
                try:
                    qry = func(**vars)

                    # does the function return a query or an error dictionary
                    if isinstance(qry, dict):
                        return qry
                    else:
                        most_recent, ids = _parse_vars(vars)
                        return dataset_query_to_json(qry, most_recent, ids)
                except TypeError as e:
                    raise HTTP(400, f"Could not parse api request: {e}")
        elif len(args) == 0:
            raise HTTP(
                400,
                f"Provide one of the following search type arguments: {', '.join(SEARCH_FUNC.keys())}",
            )
        else:
            raise HTTP(400, "Unknown arguments to search API.")

    return locals()
