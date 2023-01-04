"""A controller to expose the gazetteer as a map."""

import dateutil.parser
import requests
from collections import Counter
from gluon.contrib import simplejson
from gluon.serializers import json, loads_json

import os
from gpxpy import gpx
from safe_web_global_functions import get_frm
from shapely.geometry import shape

SFIELDS = [
    db.gazetteer.location,
    db.gazetteer.type,
    db.gazetteer.plot_size,
    db.gazetteer.fractal_order,
    db.gazetteer.transect_order,
]
"""This is a list of gazetteer table fields used for searching and download, and needs
to be updated to the gazetteer table definition used by a particular project.
"""


def gazetteer():

    """
    Controller to provide a map view of the gazetteer data and a searchable
    interface with GPX and GeoJSON download.
    """

    # If the grid has set up some search keywords, and the keywords aren't an empty
    # string then use them to select those rows, otherwise get all rows

    if "keywords" in request.get_vars and request.vars.keywords != "":
        qry = SQLFORM.build_query(SFIELDS, keywords=request.vars.keywords)
    else:
        qry = db.gazetteer

    # get the (selected) rows and turn them into geojson, ordering them
    # so that the bottom ones get added to the leaflet map first
    rws = db(qry).select(
        db.gazetteer.ALL,
        db.gazetteer.wkt_wgs84.st_asgeojson().with_alias("geojson"),
        orderby=db.gazetteer.display_order,
    )

    # Need to put together the tooltip for the gazetteer
    # using a subset of the available columns
    loc = ["<B>" + rw.gazetteer["location"] + "</B></BR>" for rw in rws]
    info = [
        [
            key + ": " + str(rw.gazetteer[key])
            for key in [
                "type",
                "plot_size",
                "parent",
                "fractal_order",
                "transect_order",
            ]
            if rw.gazetteer[key] is not None
        ]
        for rw in rws
    ]

    # combine, removing trailing break
    tooltips = [l + "</BR>".join(i) for l, i in zip(loc, info)]

    rws = [
        {"type": "Feature", "tooltip": tl, "geometry": loads_json(r.geojson)}
        for r, tl in zip(rws, tooltips)
    ]

    # provide GPX and GeoJSON downloaders and use the magic 'with_hidden_cols' suffix to
    # allow the Exporter to access fields that aren't shown in the table
    export = dict(
        gpx_with_hidden_cols=(ExporterGPX, "GPX"),
        geojson_with_hidden_cols=(ExporterGeoJSON, "GeoJson"),
        csv_with_hidden_cols=False,
        csv=False,
        xml=False,
        html=False,
        json=False,
        tsv_with_hidden_cols=False,
        tsv=False,
    )

    # hide display order from search and export
    db.gazetteer.display_order.readable = False

    form = SQLFORM.grid(
        db.gazetteer,
        fields=SFIELDS,
        csv=True,
        exportclasses=export,
        maxtextlength=250,
        deletable=False,
        editable=False,
        create=False,
        details=False,
    )

    # format the HTML to move the export button into the search console
    # get a button themed link. Check to make sure there is an export menu
    # as it will be missing if a search returns no rows
    exp_menu = form.element(".w2p_export_menu")
    if exp_menu is not None:
        exp_gpx = A(
            "Export GPX",
            _class="btn btn-default",
            _href=exp_menu[2].attributes["_href"],
            _style="padding:6px 12px;line-height:20px",
        )
        exp_geojson = A(
            "Export GeoJSON",
            _class="btn btn-default",
            _href=exp_menu[1].attributes["_href"],
            _style="padding:6px 12px;line-height:20px",
        )
        console = form.element(".web2py_console form")
        console.insert(len(console), CAT(exp_gpx, exp_geojson))

        # get the existing export menu index (a DIV within FORM) and delete it
        export_menu_idx = [x.attributes["_class"] for x in form].index(
            "w2p_export_menu"
        )
        del form[export_menu_idx]

    return dict(form=form, sitedata=json(rws))


class ExporterGPX(object):

    """
    Used to export a GPX file of the selected rows in SQLFORM grid
    """

    file_ext = "gpx"
    content_type = "text/xml"

    def __init__(self, rows):
        self.rows = rows

    def export(self):
        if self.rows:
            # create a new gpx file
            gpx_data = gpx.GPX()

            # exclude rows with no centroid data (polylines at present)
            to_gpx = (rw for rw in self.rows if rw.centroid_x is not None)

            # add the centroids into the file
            for pt in to_gpx:
                gpx_data.waypoints.append(
                    gpx.GPXWaypoint(
                        name=pt.location,
                        longitude=pt.centroid_x,
                        latitude=pt.centroid_y,
                    )
                )

            return gpx_data.to_xml()
        else:
            return ""


class ExporterGeoJSON(object):

    """
    Used to export a GPX file of the selected rows in SQLFORM grid
    """

    file_ext = "geojson"
    content_type = "application/vnd.geo+json"

    def __init__(self, rows):
        self.rows = rows

    def export(self):
        if self.rows:

            # get a list of dictionaries of the values
            ft_as_dicts = list(self.rows.as_dict().values())

            # pop out the geometry components and id
            id_number = [ft.pop("id") for ft in ft_as_dicts]

            # Get the locations - for geojson, we need an id, a geometry and a dictionary
            # of properties. This query uses the with_alias() to strucure the results with
            # id and geojson outside of the 'gazetteer' table dictionary, making it really
            # simple to restucture them into a geojson Feature entry
            locations = (
                db(db.gazetteer.id.belongs(id_number))
                .select(
                    db.gazetteer.id.with_alias("id"),
                    db.gazetteer.location,
                    SFIELDS,
                    db.gazetteer.wkt_wgs84.st_asgeojson().with_alias("geojson"),
                )
                .as_list()
            )

            # assemble the features list - postgres returns ST_AsGeoJSON as a string, so
            # this has to be converted back into a dictionary.
            features = [
                {
                    "type": "Feature",
                    "id": loc["id"],
                    "properties": loc["gazetteer"],
                    "geometry": loads_json(loc["geojson"]),
                }
                for loc in locations
            ]

            # embed that in the Feature collection
            feature_collection = {
                "type": "FeatureCollection",
                "crs": {
                    "type": "name",
                    "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"},
                },
                "features": features,
            }

            return simplejson.dumps(feature_collection)
        else:
            return ""
