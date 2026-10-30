from django.contrib import admin

from admin_helpers import ReadOnlyAdmin
from datasets.models import Dataset, Taxa

# Register models using read only admin class
admin.site.register(Dataset, ReadOnlyAdmin)
admin.site.register(Taxa, ReadOnlyAdmin)
