from django.contrib import admin

from datasets.models import Dataset, Taxa

# Register your models here.
admin.site.register(Dataset)
admin.site.register(Taxa)
