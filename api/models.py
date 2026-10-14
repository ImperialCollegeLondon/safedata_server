from django.db import models


class ServerMessage(models.Model):
    """
    A single, admin-editable message accessed via /api/message.

    Deliberately a single row: simple admin-editable text, not a queue or
    schedule of multiple messages.
    """

    message = models.TextField(
        blank=True,
        help_text="Shown to safedata clients on load. Leave blank for no message.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.message[:60] or "(no message set)"

    def save(self, *args, **kwargs):
        # Enforce single-row: always overwrite pk=1 rather than allowing
        # multiple message rows to accumulate.
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def current(cls) -> "ServerMessage | None":
        return cls.objects.first()
