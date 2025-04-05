from django.core.management.base import BaseCommand
from api.utils import google_sheets_reader


class Command(BaseCommand):
    help = 'Uploads questions from Google Sheets to the database'

    def handle(self, *args, **kwargs):
        google_sheets_reader.upload_ai_questions_from_sheet('15WeAkV4DPNcr4AdBWcZFbr2DrGNfj30mzGQEOcnqu3A', 'Basic Theory')
        self.stdout.write(self.style.SUCCESS('Successfully uploaded questions'))