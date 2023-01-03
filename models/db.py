# -*- coding: utf-8 -*-

# -------------------------------------------------------------------------
# AppConfig configuration made easy. Look inside private/appconfig.ini
# Auth is for authenticaiton and access control
# -------------------------------------------------------------------------
from gluon.contrib.appconfig import AppConfig
from gluon.tools import Auth
from gluon import current

# -------------------------------------------------------------------------
# This scaffolding model makes your app work on Google App Engine too
# File is released under public domain and you can use without limitations
# -------------------------------------------------------------------------

if request.global_settings.web2py_version < "2.15.5":
    raise HTTP(500, "Requires web2py 2.15.5 or newer")

# -------------------------------------------------------------------------
# if SSL/HTTPS is properly configured and you want all HTTP requests to
# be redirected to HTTPS, uncomment the line below:
# -------------------------------------------------------------------------
# request.requires_https()

# -------------------------------------------------------------------------
# once in production, remove reload=True to gain full speed
# -------------------------------------------------------------------------
configuration = AppConfig(reload=True)


db = DAL(
    configuration.get("db.uri"),
    pool_size=configuration.get("db.pool_size"),
    migrate_enabled=configuration.get("db.migrate"),
    check_reserved=["all"],
)

# Store db and configuration in the current object so they can be access by modules
current.db = db
current.configuration = configuration

# -------------------------------------------------------------------------
# by default give a view/generic.extension to all actions from localhost
# none otherwise. a pattern can be 'controller/function.extension'
# -------------------------------------------------------------------------
response.generic_patterns = []
if request.is_local and not configuration.get("app.production"):
    response.generic_patterns.append("*")

# -------------------------------------------------------------------------
# choose a style for forms
# -------------------------------------------------------------------------
response.formstyle = "bootstrap4_inline"
response.form_label_separator = ""

# -------------------------------------------------------------------------
# (optional) optimize handling of static files
# -------------------------------------------------------------------------
# response.optimize_css = 'concat,minify,inline'
# response.optimize_js = 'concat,minify,inline'

# -------------------------------------------------------------------------
# (optional) static assets folder versioning
# -------------------------------------------------------------------------
# response.static_version = '0.0.0'

# -------------------------------------------------------------------------
# Here is sample code if you need for
# - email capabilities
# - authentication (registration, login, logout, ... )
# - authorization (role based authorization)
# - services (xml, csv, json, xmlrpc, jsonrpc, amf, rss)
# - old style crud actions
# (more options discussed in gluon/tools.py)
# -------------------------------------------------------------------------

# host names must be a list of allowed host names (glob syntax allowed)
auth = Auth(db, host_names=configuration.get("host.names"))

# -------------------------------------------------------------------------
# create all tables needed by auth, maybe add a list of extra fields
# -------------------------------------------------------------------------
auth.settings.extra_fields["auth_user"] = []
auth.define_tables(username=False, signature=False)

# -------------------------------------------------------------------------
# configure email
# -------------------------------------------------------------------------
mail = auth.settings.mailer
mail.settings.server = (
    "logging" if request.is_local else configuration.get("smtp.server")
)
mail.settings.sender = configuration.get("smtp.sender")
mail.settings.login = configuration.get("smtp.login")
mail.settings.tls = configuration.get("smtp.tls") or False
mail.settings.ssl = configuration.get("smtp.ssl") or False

# -------------------------------------------------------------------------
# configure auth policy
# -------------------------------------------------------------------------
auth.settings.registration_requires_verification = False
auth.settings.registration_requires_approval = False
auth.settings.reset_password_requires_verification = True

# -------------------------------------------------------------------------
# read more at http://dev.w3.org/html5/markup/meta.name.html
# -------------------------------------------------------------------------
response.meta.author = configuration.get("app.author")
response.meta.description = configuration.get("app.description")
response.meta.keywords = configuration.get("app.keywords")
response.meta.generator = configuration.get("app.generator")
response.show_toolbar = configuration.get("app.toolbar")

# -------------------------------------------------------------------------
# your http://google.com/analytics id
# -------------------------------------------------------------------------
response.google_analytics_id = configuration.get("google.analytics_id")

# -------------------------------------------------------------------------
# maybe use the scheduler
# -------------------------------------------------------------------------
if configuration.get("scheduler.enabled"):
    from gluon.scheduler import Scheduler

    scheduler = Scheduler(db, heartbeat=configuration.get("scheduler.heartbeat"))

# -------------------------------------------------------------------------
# Tables
# -------------------------------------------------------------------------

# -------------------------------------------------------------------------
# Tables - resources
# Gazetteer definition can be extended
# -------------------------------------------------------------------------

db.define_table(
    "gazetteer",
    Field("location_name", "string", unique=True),
    Field("location_type", "string"),
    Field("centroid_x", "float"),
    Field("centroid_y", "float"),
    Field("bbox_xmin", "float"),
    Field("bbox_xmax", "float"),
    Field("bbox_ymin", "float"),
    Field("bbox_ymax", "float"),
    Field("wkt_wgs84", "geometry()"),
    # Create local projected coordinate geometry, setting schema, EPSG, ndim
    Field("wkt_local", f"geometry(public, {configuration.get('geo.local_epsg')}, 2)"),
)


# Aliases location names - cannot use a value already in the gazetteer locations
# This table identifies location names that equate to an official name in the
# gazetteer. The field dataset_id allows a name in a specific dataset to be adopted
# retrospectively: all NEW locations in a dataset should be checked to see if they
# appear in this table and, if so, they can point to a gazetteer location. The
# zenodo_record_id allows these names only to be unique within a dataset. If
# zenodo_record_id is None, then the values are general aliases

db.define_table(
    "gazetteer_alias",
    Field(
        "zenodo_record_id",
        "integer",
        requires=IS_NULL_OR(IS_IN_DB(db, "published_datasets.zenodo_record_id")),
    ),
    Field("location_name", "string", requires=IS_IN_DB(db, "gazetteer.locations")),
    Field("location_alias", "string", requires=IS_NOT_IN_DB(db, "gazetteer.locations")),
)

# The combination of dataset_id and location_alias needs to be unique.
# Normally this would be a multi column primary key but is achieved here
# using the callback defined below the table

db.gazetteer_alias._before_insert.append(
    lambda r: db(
        (db.gazetteer_alias.zenodo_record_id == r["zenodo_record_id"])
        & (db.gazetteer_alias.alias == r["alias"])
    ).select()
)


# -------------------------------------------------------------------------
# Datasets
# -------------------------------------------------------------------------

db.define_table(
    "published_datasets",
    # fields to handle the file upload and checking
    Field("upload_datetime", "datetime"),
    # Fields to hold the dataset metadata
    Field("dataset_title", "text"),
    Field("dataset_access", "string"),
    Field("dataset_embargo", "date"),
    Field("dataset_conditions", "text"),
    Field("dataset_description", "text"),
    Field("dataset_metadata", "json"),
    # Fields to hold publication data - most data is stored in the metadata
    # field as JSON, but for quick recall, a few are stored directly.
    Field("most_recent", "boolean"),
    Field("publication_date", "datetime"),
    Field("zenodo_metadata", "json"),
    Field("zenodo_record_id", "integer"),
    Field("zenodo_record_doi", "string"),
    Field("zenodo_record_badge", "string"),
    Field("zenodo_concept_id", "integer"),
    Field("zenodo_concept_doi", "string"),
    Field("zenodo_concept_badge", "string"),
    Field("geographic_extent", "geometry()"),
    Field("geographic_extent_utm50n", "geometry(public, 32650, 2)"),
    Field("temporal_extent_start", "date"),
    Field("temporal_extent_end", "date"),
    Field("dataset_history", "text"),
)

# -----------------------------------------------------------------------------
# DATASET INDEX TABLE DEFINITIONS
# - these tables hold information about published datasets.
# - information is available for each published version
# - In some ways it would be neater for these tables to use the
#   zenodo record id as the key back to the datasets table, but
#   web2py can only achieve that using the IS_IN_DB validator rather
#   than a DB level foreign key
# -----------------------------------------------------------------------------

db.define_table(
    "dataset_keywords",
    Field("dataset_id", "reference published_datasets"),
    Field("keyword", "string"),
)

db.define_table(
    "dataset_taxa",
    Field("dataset_id", "reference published_datasets"),
    Field("taxon_auth", "string"),
    Field("worksheet_name", "string"),
    Field("taxon_id", "integer"),
    Field("parent_id", "integer"),
    Field("taxon_name", "string"),
    Field("taxon_rank", "string"),
    Field("taxon_status", "string"),
)

db.define_table(
    "dataset_files",
    Field("dataset_id", "reference published_datasets"),
    Field("checksum", "string", length=32),
    Field("filename", "string"),
    Field("filesize", "bigint"),
    Field("file_zenodo_id", "string", length=36),
    Field("download_link", "string"),
)

db.define_table(
    "dataset_locations",
    Field("dataset_id", "reference published_datasets"),
    Field("name", "string"),
    Field("new_location", "boolean"),
    Field("loc_type", "string"),
    Field("wkt_wgs84", "geometry()"),
    # Create local projected coordinate geometry, setting schema, EPSG, ndim
    Field("wkt_local", f"geometry(public, {configuration.get('geo.local_epsg')}, 2)"),
)

db.define_table(
    "dataset_worksheets",
    Field("dataset_id", "reference published_datasets"),
    Field("name", "string"),
    Field("description", "text"),
    Field("title", "string"),
    Field("external_file", "string"),
    Field("n_data_row", "integer"),
    Field("max_col", "integer"),
)

db.define_table(
    "dataset_fields",
    Field("dataset_id", "reference published_datasets"),
    Field("worksheet_id", "reference dataset_worksheets"),
    Field("field_type", "string"),
    Field("description", "text"),
    Field("levels", "text"),
    Field("units", "string"),
    Field("taxon_name", "string"),
    Field("taxon_field", "string"),
    Field("interaction_field", "string"),
    Field("interaction_name", "string"),
    Field("field_method", "text"),
    Field("field_name", "string"),
)

db.define_table(
    "dataset_authors",
    Field("dataset_id", "reference published_datasets"),
    Field("affiliation", "string"),
    Field("email", "string"),
    Field("name", "string"),
    Field("orcid", "string"),
)

db.define_table(
    "dataset_funders",
    Field("dataset_id", "reference published_datasets"),
    Field("body", "string"),
    Field("funder_ref", "string"),
    Field("funder_type", "string"),
    Field("url", "string"),
)

db.define_table(
    "dataset_permits",
    Field("dataset_id", "reference published_datasets"),
    Field("authority", "string"),
    Field("permit_number", "string"),
    Field("permit_type", "string"),
)


# -------------------------------------------------------------------------
# after defining tables, uncomment below to enable auditing
# -------------------------------------------------------------------------
# auth.enable_record_versioning(db)
