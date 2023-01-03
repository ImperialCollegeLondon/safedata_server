# The `safedata_server` application

This is a web application written using the Web2Py framework that implements the
API used by the `safedata_validator` and `safedata` packages for publishing and
using sets of linked scientific datasets.

## Installation

These notes are very brief but the main requirements are:

* Setup and configure a web server serving Web2Py applications

* The server will also need to provide a PostgreSQL server with PostGIS
  installed in order to handle data storage for the web application and the
  underlying GIS operations.

* Create a PostgreSQL database user for the web application and then a database
  to be used by the application, with PostGIS enabled.

```SQL
-- create a postgis enabled template
\c postgres
CREATE DATABASE template_postgis;
UPDATE pg_database SET datistemplate = TRUE WHERE datname = 'template_postgis';
\c template_postgis
CREATE EXTENSION postgis;
-- Setup a PostGIS enabled database for the web application
CREATE USER safedata_server_admin WITH PASSWORD 'password';
CREATE DATABASE safedata_server 
    WITH TEMPLATE template_postgis OWNER safedata_server_admin;
```

* Install this application into the Web2Py `applications` directory.
* Update the file in `private/appconfig_template.ini` to include the
  connection string for the database and to include a secure token
  used to validate the upload of new dataset details.

```ini
[db]
uri = postgres://safedata_server_admin:password@localhost/safedata_server
```

* Configure the Web2Py routes to use this as the default application.

## Resources

The datasets are validated against some local resources

### Gazetteer

Implement local PCS and map
