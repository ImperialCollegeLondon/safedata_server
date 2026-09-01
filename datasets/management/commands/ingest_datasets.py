# datasets/management/commands/ingest_datasets.py
"""Management command to batch-ingest safedata_validator JSON exports
from a directory.

Usage:
    uv run python manage.py ingest_datasets path/to/directory/
"""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from datasets.ingest import DatasetIngestError, ingest_dataset


class Command(BaseCommand):
    help = "Ingest all dataset JSON exports in a directory, one dataset per file."

    def add_arguments(self, parser):
        parser.add_argument(
            "directory", type=str, help="Directory containing dataset .json files."
        )

    def handle(self, *args, **options):
        directory = Path(options["directory"])

        if not directory.is_dir():
            raise CommandError(f"{directory} is not a directory.")

        json_files = sorted(directory.glob("*.json"))
        if not json_files:
            self.stdout.write(self.style.WARNING(f"No .json files found in {directory}."))
            return

        succeeded = []
        failed = []

        for path in json_files:
            try:
                with open(path) as f:
                    data = json.load(f)
            except json.JSONDecodeError as exc:
                failed.append((path, f"invalid JSON: {exc}"))
                continue

            try:
                dataset = ingest_dataset(data)
                succeeded.append((path, dataset.id))
            except DatasetIngestError as exc:
                failed.append((path, str(exc)))

        self.stdout.write(f"\nSucceeded: {len(succeeded)}")
        for path, dataset_id in succeeded:
            self.stdout.write(
                self.style.SUCCESS(f"  OK   {path.name} -> Dataset id {dataset_id}")
            )

        self.stdout.write(f"\nFailed: {len(failed)}")
        for path, error in failed:
            self.stdout.write(self.style.ERROR(f"  FAIL {path.name}: {error}"))