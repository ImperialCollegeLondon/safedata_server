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
                _href=URL("default", "view_dataset", vars={"id": row.zenodo_record_id}),
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


def view_dataset():

    """
    View of a specific version of a dataset, taking the zenodo record id as the
    id parameter, but which also shows other published versions of the dataset concept.
    """

    ds_id = request.vars["id"]

    if ds_id is None:
        # no id provided
        session.flash = "Missing dataset id"
        redirect(URL("datasets", "view_datasets"))

    try:
        ds_id = int(ds_id)
    except ValueError:
        session.flash = "Dataset id is not an integer"
        redirect(URL("datasets", "view_datasets"))

    # Does the record identify a specific version
    record = db(db.published_datasets.zenodo_record_id == ds_id).select().first()

    # If not, does it identify a concept, so get the most recent
    if record is None:
        record = (
            db(
                (db.published_datasets.zenodo_concept_id == ds_id)
                & (db.published_datasets.most_recent == True)
            )
            .select()
            .first()
        )
        # Otherwise, bail
        if record is None:
            # non-existent id provided
            session.flash = "Database record id does not exist"
            redirect(URL("datasets", "view_datasets"))
        else:
            ds_id = record.zenodo_record_id

    # get the version history
    qry = db.published_datasets.zenodo_concept_id == record.zenodo_concept_id

    history = db(qry).select(
        db.published_datasets.id,
        db.published_datasets.publication_date,
        # db.published_datasets.uploader_id,
        db.published_datasets.zenodo_record_badge,
        db.published_datasets.zenodo_record_doi,
        db.published_datasets.zenodo_record_id,
        orderby=~db.published_datasets.publication_date,
    )

    # style that into a table showing the currently viewed version

    view = SPAN(
        _class="glyphicon glyphicon-eye-open", _style="color:green;font-size: 1.4em;"
    )
    alt = SPAN(
        _class="glyphicon glyphicon-eye-close",
        _style="color:grey;font-size: 1.4em;",
        _title="View this version",
    )

    history_table = TABLE(
        TR(
            TH("Viewing"),
            TH("Version publication date"),  # TH('Uploaded by'),
            TH("Zenodo DOI"),
        ),
        *[
            TR(
                TD(view)
                if r.zenodo_record_id == ds_id
                else TD(A(alt, _href=URL(vars={"id": r.zenodo_record_id}))),
                TD(r.publication_date),
                # TD(r.uploader_id.first_name + ' ' + r.uploader_id.last_name),
                TD(A(IMG(_src=r.zenodo_record_badge), _href=r.zenodo_record_doi)),
            )
            for r in history
        ],
        _width="100%",
        _class="table table-striped table-bordered"
    )

    # get the description
    description = XML(dataset_description(record, gemini_id=ds_id))

    # get projects
    # db(db)

    return dict(record=record, description=description, history_table=history_table)


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
