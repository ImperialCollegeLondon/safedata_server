from django.contrib import admin

from api.models import ServerMessage

@admin.register(ServerMessage)
class ServerMessageAdmin(admin.ModelAdmin):
    list_display = ("message", "updated_at")

    def has_add_permission(self, request):
        # Only one row should ever exist - edit the existing one instead
        # of creating new rows.
        return not ServerMessage.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
