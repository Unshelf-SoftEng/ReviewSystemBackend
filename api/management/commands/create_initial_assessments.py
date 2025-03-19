from django.core.management.base import BaseCommand
from api.utils import google_sheets_reader


class Command(BaseCommand):
    help = 'Uploads questions from Google Sheets to the database'

    def handle(self, *args, **kwargs):
        return