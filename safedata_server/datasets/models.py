from django.db import models



class Dataset(models.Model):
    """Dataset model representing one zenodo record. Placeholder."""
    
    zenodo_record_id: models.IntegerField = models.IntegerField(primary_key=True)

    def __str__(self):
        return str(self.zenodo_record_id)