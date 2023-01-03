# The `safedata_server` application

This is a web application written using the Web2Py framework that implements the
API used by the `safedata_validator` and `safedata` packages for publishing and
using sets of linked scientific datasets.

## Installation

These notes are very brief but the main requirements are:

* Setup and configure a web server serving [Web2Py](http://www.web2py.com) web
  applications.

* The server will also need to be able to access a [PostgreSQL](https://postgresql.org)
  server  to handle data storage for the web application and the underlying GIS
  operations. That could be installed on the  web server or in a separate database
  server.

* `safedata_server` uses GIS functionality within PostgreSQL provided by
  [PostGIS](https://postgis.net), so you will need to install this on the database
  server and then create a template database with PostGIS enabled.

```SQL
-- create a postgis enabled template
\c postgres
CREATE DATABASE template_postgis;
UPDATE pg_database SET datistemplate = TRUE WHERE datname = 'template_postgis';
\c template_postgis
CREATE EXTENSION postgis;
```

* Create a [PostgreSQL](https://postgresql.org) database user for the web application
  and then use the PostGIS template to create a database to be used by the application.

```SQL
-- Setup a PostGIS enabled database for the web application
CREATE USER safedata_server_admin WITH PASSWORD 'password';
CREATE DATABASE safedata_server 
    WITH TEMPLATE template_postgis OWNER safedata_server_admin;
```

* Clone this repository into the Web2Py `applications` directory.

* Update the file in `private/appconfig_template.ini` to include the connection string
  for the database and to include a secure token used to validate metadata upload.

```ini
[db]
uri = postgres://safedata_server_admin:password@localhost/safedata_server
```

* Configure the Web2Py routes to use this as the default application.

## Usage

The webserver is used to ingest metadata about datasets that have been validated and
published using the
[`safedata_validator`](https://safedata-validator.readthedocs.io/en/latest/) python
package and then serve that metadata out to users, principally via the
[`safedata`](https://imperialcollegelondon.github.io/safedata/index.html) R package.
