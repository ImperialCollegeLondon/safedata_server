# -*- coding: utf-8 -*-
# this file is released under public domain and you can use without limitations

# ----------------------------------------------------------------------------------------------------------------------
# this is the main application menu add/remove items as required
# ----------------------------------------------------------------------------------------------------------------------

response.menu = [
    (T("Datasets"), False, URL("default", "datasets")),
    (T("API"), False, URL("api", "index")),
    (T("Database"), False, URL("appadmin", "index")),
]
