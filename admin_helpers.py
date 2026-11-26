from django.contrib.admin import ModelAdmin
from django.contrib.gis.admin import GISModelAdmin


class ReadOnlyAdmin(ModelAdmin):
    """Class implementing read-only model views in admin interface."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class ReadOnlyGISAdmin(GISModelAdmin):
    """Class implementing read-only GIS model views in admin interface.

    This doesn't preserve the GIS view of the GIS fields in the admin table.
    """

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
