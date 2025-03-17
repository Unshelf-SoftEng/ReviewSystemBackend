from django.core.management.base import BaseCommand
from api.utils import google_sheets_reader


class Command(BaseCommand):
    help = 'Uploads questions from Google Sheets to the database'

    def handle(self, *args, **kwargs):

        spreadsheet_id = "160BuIjTsa411HjqhutWz4mkG0HPxarfeBJpsRG-Ijxg"
        range_name = "Sheet1"

        google_sheets_reader.upload_lessons_from_sheet(spreadsheet_id, range_name)
        self.stdout.write(self.style.SUCCESS('Successfully uploaded lessons'))