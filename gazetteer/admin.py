from django.contrib import admin
from django.contrib.gis.admin import GISModelAdmin

from gazetteer.models import Gazetteer, GazetteerAlias

# Register your models here.


@admin.register(Gazetteer)
class GazetteerAdmin(GISModelAdmin):
    list_display = ("location",)
    search_fields = ("location",)
    ordering = ("location",)


@admin.register(GazetteerAlias)
class GazetteerAliasAdmin(admin.ModelAdmin):
    list_display = ("alias", "location", "dataset")
    search_fields = ("alias", "location__location")
    list_filter = ("dataset",)