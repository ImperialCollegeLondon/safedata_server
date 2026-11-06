from django.contrib import admin
from django.contrib.gis.admin.options import GeoModelAdminMixin

from admin_helpers import ReadOnlyAdmin
from gazetteer.models import Gazetteer, GazetteerAlias

# Register your models here.


@admin.register(Gazetteer)
class GazetteerAdmin(ReadOnlyAdmin, GeoModelAdminMixin):
    # Can't work out out to make this read only without breaking the
    # GIS display of fields
    list_display = ("location",)
    search_fields = ("location",)
    ordering = ("location",)


@admin.register(GazetteerAlias)
class GazetteerAliasAdmin(ReadOnlyAdmin):
    list_display = ("alias", "location", "dataset")
    search_fields = ("alias", "location__location")
    list_filter = ("dataset",)
