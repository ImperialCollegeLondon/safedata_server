"""This module provides a simple function used to maintain the resources hash file used
for the gazetteer, aliases and datasets downloads."""

import json
from hashlib import md5

from django.core.files.storage import FileSystemStorage


def update_resource_hashes(key, data):
    """Generates and updates the resources hash file.

    Note that FileSystemStorage defaults to the MEDIA_ROOT directory that is used to
    serve resource files via MEDIA_URL. The function handles the generation of the file
    if it is not already present.
    """
    if not FileSystemStorage().exists("hashes.json"):
        hashes = {
            "gazetteer.geojson": None,
            "location_aliases.csv": None,
            "index.json": None,
        }
    else:
        with FileSystemStorage().open("hashes.json", "r") as hashfile:
            hashes = json.load(hashfile)

    hashes[key] = md5(data).hexdigest()

    with FileSystemStorage().open("hashes.json", "w") as hashfile:
        json.dump(hashes, hashfile)
