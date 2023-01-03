# -*- coding: utf-8 -*-
import datetime
import inspect
import json

# ---- example index page ----
def index():
    redirect(URL("default", "datasets"))
    return dict()


def datasets():
    """Display datasets.

    Grid view to display datasets that have been posted.
    """

    def _access(row):

        row.dataset_access
        ret = SPAN("O", _class="badge", _style="background-color:green;font-size: 1em;")

        if (
            row.dataset_access == "embargo"
            and row.dataset_embargo > datetime.date.today()
        ):
            ret = SPAN(
                "E",
                _class="badge",
                _style="background-color:orange;font-size: 1em;",
                _title=row.dataset_embargo,
            )
        elif row.dataset_access == "restricted":
            ret = SPAN(
                "R",
                _class="badge",
                _style="background-color:red;font-size: 1em;",
                _title=row.dataset_conditions,
            )

        return ret

    # format fields for the display
    db.published_datasets.zenodo_concept_badge.represent = lambda value, row: A(
        IMG(_src=value), _href=row.zenodo_concept_doi
    )
    db.published_datasets.publication_date.represent = (
        lambda value, row: value.date().isoformat() if value else "---"
    )
    db.published_datasets.dataset_access.represent = lambda value, row: _access(row)

    # hide fields used in table prep
    db.published_datasets.zenodo_record_id.readable = False
    db.published_datasets.zenodo_concept_doi.readable = False
    db.published_datasets.dataset_embargo.readable = False
    db.published_datasets.dataset_conditions.readable = False

    # button to link to custom view
    links = [
        dict(
            header="",
            body=lambda row: A(
                "Details",
                _class="button btn btn-sm btn-default",
                _href=URL(
                    "datasets", "view_dataset", vars={"id": row.zenodo_record_id}
                ),
            ),
        )
    ]

    # Display those records as a grid
    form = SQLFORM.grid(
        db.published_datasets.most_recent == True,
        fields=[  # db.published_datasets.project_id,
            db.published_datasets.publication_date,
            db.published_datasets.dataset_title,
            db.published_datasets.dataset_access,
            db.published_datasets.dataset_embargo,
            db.published_datasets.dataset_conditions,
            db.published_datasets.zenodo_record_id,
            db.published_datasets.zenodo_concept_badge,
            db.published_datasets.zenodo_concept_doi,
        ],
        headers={"published_datasets.zenodo_concept_badge": "DOI"},
        orderby=[~db.published_datasets.publication_date],
        maxtextlength=100,
        deletable=False,
        editable=False,
        details=False,
        create=False,
        csv=False,
        links=links,
    )

    return dict(form=form)


# ---- Action for login/register/etc (required for auth) -----
def user():
    """
    exposes:
    http://..../[app]/default/user/login
    http://..../[app]/default/user/logout
    http://..../[app]/default/user/register
    http://..../[app]/default/user/profile
    http://..../[app]/default/user/retrieve_password
    http://..../[app]/default/user/change_password
    http://..../[app]/default/user/bulk_register
    use @auth.requires_login()
        @auth.requires_membership('group name')
        @auth.requires_permission('read','table name',record_id)
    to decorate functions that need access control
    also notice there is:
        http://..../[app]/appadmin/manage/auth
    to allow administrator to manage users
    """
    return dict(form=auth())


# ---- action to server uploaded static content (required) ---
@cache.action()
def download():
    """
    allows downloading of uploaded files
    http://..../[app]/default/download/[filename]
    """
    return response.download(request, db)
