from django.core.management.base import BaseCommand
from api.utils import google_sheets_reader


class Command(BaseCommand):
    help = 'Uploads questions from Google Sheets to the database'

    def handle(self, *args, **kwargs):
        google_sheets_reader.upload_pretest_from_sheet('1bFsKUlbIzIcvD4mEgPX0uy3q7bYoPHx0zyFwzLGlPVU', 'Pretest')
        self.stdout.write(self.style.SUCCESS('Successfully uploaded questions'))