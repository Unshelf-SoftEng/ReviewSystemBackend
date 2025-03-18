from django.core.management.base import BaseCommand
from api.utils import google_sheets_reader


class Command(BaseCommand):
    help = 'Uploads questions from Google Sheets to the database'

    def handle(self, *args, **kwargs):
        google_sheets_reader.upload_questions_from_sheet('1h0taQaf0d8Brx5qCouofPQfpQsrxdfgB-VT9c6Thxic', 'All')
        self.stdout.write(self.style.SUCCESS('Successfully uploaded questions'))