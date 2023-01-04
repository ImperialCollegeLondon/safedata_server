"""
GAZETTEER
- Two tables: one holds the set of recognized locations and the other holds
  aliases for locations.
- For a given project, the gazetteer table needs to be aligned to the properties used
  in the gazetteer GeoJSON. The location field is mandatory and the two wkt_ fields are
  used internally to store lat long and local PCS data.
"""

db.define_table(
    "gazetteer",
    Field("location", "string", unique=True),
    Field("wkt_wgs84", "geometry()"),
    Field("wkt_local", f"geometry(public, {configuration.get('geo.local_epsg')}, 2)"),
)


"""
Aliases location names - cannot use a value already in the gazetteer locations
This table identifies location names that equate to an official name in the
gazetteer. The field dataset_id allows a name in a specific dataset to be adopted
retrospectively: all NEW locations in a dataset should be checked to see if they
appear in this table and, if so, they can point to a gazetteer location. The
zenodo_record_id allows these names only to be unique within a dataset. If
zenodo_record_id is None, then the values are general aliases
"""

db.define_table(
    "gazetteer_alias",
    Field(
        "zenodo_record_id",
        "integer",
        requires=IS_NULL_OR(IS_IN_DB(db, "published_datasets.zenodo_record_id")),
    ),
    Field("location", "string", requires=IS_IN_DB(db, "gazetteer.locations")),
    Field("alias", "string", requires=IS_NOT_IN_DB(db, "gazetteer.locations")),
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
