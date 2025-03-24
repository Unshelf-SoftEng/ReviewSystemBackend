from django.core.management.base import BaseCommand
from api.utils.google_sheets_reader import upload_lessons_from_sheet


class Command(BaseCommand):
    help = 'Uploads lessons, chapters, and sections from separate Google Sheets to the database'

    def handle(self, *args, **kwargs):
        lesson_spreadsheet_id = "160BuIjTsa411HjqhutWz4mkG0HPxarfeBJpsRG-Ijxg"
        chapter_spreadsheet_id = "160BuIjTsa411HjqhutWz4mkG0HPxarfeBJpsRG-Ijxg"
        section_spreadsheet_id = "160BuIjTsa411HjqhutWz4mkG0HPxarfeBJpsRG-Ijxg"

        lesson_range = "Lessons"
        chapter_range = "Chapters"
        section_range = "Sections"

        upload_lessons_from_sheet(lesson_spreadsheet_id, lesson_range, chapter_spreadsheet_id, chapter_range,
                                  section_spreadsheet_id, section_range)
        self.stdout.write(self.style.SUCCESS('Successfully uploaded lessons, chapters, and sections'))