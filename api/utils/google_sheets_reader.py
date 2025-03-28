from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from api.models import Question, Category, Lesson, Chapter, Section
import json

CATEGORY_MAPPING = {
    "Basic Theory": 1,
    "Computer System": 2,
    "Technology Element": 3,
    "Development Technology": 4,
    "Project Management": 5,
    "Service Management": 6,
    "Business Strategy": 7,
    "System Strategy": 8,
    "Corporate and Legal Affairs": 9,
}


# Function to get the Google Sheets API service
def get_google_sheets_service():
    creds = service_account.Credentials.from_service_account_file(
        'api/utils/credentials.json',
        scopes=['https://www.googleapis.com/auth/spreadsheets.readonly'],
    )
    return build('sheets', 'v4', credentials=creds)


# Function to get data from Google Sheets
def get_sheet_data(spreadsheet_id, range_name):
    try:
        service = get_google_sheets_service()
        sheet = service.spreadsheets()
        result = sheet.values().get(spreadsheetId=spreadsheet_id, range=range_name).execute()
        return result.get('values', [])
    except HttpError as err:
        print(f"Error fetching sheet data: {err}")
        return None


# Function to upload questions to the database
def upload_questions_from_sheet(spreadsheet_id, range_name):
    sheet_data = get_sheet_data(spreadsheet_id, range_name)

    if sheet_data:
        for row in sheet_data[1:]:
            if len(row) < 2 or not row[0]:
                continue

            question_id = row[1]
            question_text = row[2] if len(row) > 2 else ''
            image_url = row[3] if len(row) > 3 else None

            choices = {
                'a': row[4] if len(row) > 4 else '',
                'b': row[5] if len(row) > 5 else '',
                'c': row[6] if len(row) > 6 else '',
                'd': row[7] if len(row) > 7 else ''
            }
            correct_answer = row[8] if len(row) > 8 else ''
            category_name = row[9] if len(row) > 9 else ''
            difficulty = float(row[10]) if len(row) > 10 else 0.0
            discrimination = float(row[11]) if len(row) > 11 else 1.0
            guessing = float(row[12]) if len(row) > 12 else 0.0

            category_id = CATEGORY_MAPPING.get(category_name, None)
            if category_id is None:
                print(f"Category '{category_name}' not found.")
                continue

            category = Category.objects.get(id=category_id)

            existing_question = Question.objects.filter(id=question_id).first()

            if existing_question:
                Question.objects.filter(id=question_id).update(
                    question_text=question_text,
                    image_url=image_url,
                    category=category,
                    difficulty=difficulty,
                    discrimination=discrimination,
                    guessing=guessing,
                    choices=choices,
                    correct_answer=correct_answer
                )

                print('Updated Question', question_id)

            else:
                # Create the question if it does not exist
                Question.objects.create(
                    id=question_id,
                    question_text=question_text,
                    image_url=image_url,
                    category=category,
                    difficulty=difficulty,
                    discrimination=discrimination,
                    guessing=guessing,
                    choices=choices,
                    correct_answer=correct_answer
                )


def upload_pretest_from_sheet(spreadsheet_id, range_name):
    sheet_data = get_sheet_data(spreadsheet_id, range_name)

    if sheet_data:
        for row in sheet_data[1:]:
            if len(row) < 2 or not row[0]:
                continue

            question_id = row[1]
            question_text = row[2]
            image_url = row[3] if len(row) > 3 else None

            choices = {
                'a': row[4] if len(row) > 4 else '',
                'b': row[5] if len(row) > 5 else '',
                'c': row[6] if len(row) > 6 else '',
                'd': row[7] if len(row) > 7 else ''
            }
            correct_answer = row[8] if len(row) > 8 else ''
            category_name = row[9] if len(row) > 9 else ''
            difficulty = float(row[10]) if len(row) > 10 else 0.0
            discrimination = float(row[11]) if len(row) > 11 else 1.0
            guessing = float(row[12]) if len(row) > 12 else 0.0

            category_id = CATEGORY_MAPPING.get(category_name, None)
            if category_id is None:
                print(f"Category '{category_name}' not found.")
                continue

            category = Category.objects.get(id=category_id)

            existing_question = Question.objects.filter(id=question_id).first()

            if existing_question:
                Question.objects.filter(id=question_id).update(
                    question_text=question_text,
                    image_url=image_url,
                    category=category,
                    difficulty=difficulty,
                    discrimination=discrimination,
                    guessing=guessing,
                    choices=choices,
                    correct_answer=correct_answer
                )
                print('Updated Question', question_id)

            else:
                Question.objects.create(
                    id=question_id,
                    question_text=question_text,
                    image_url=image_url,
                    category=category,
                    difficulty=difficulty,
                    discrimination=discrimination,
                    guessing=guessing,
                    choices=choices,
                    correct_answer=correct_answer
                )
                print('Created Question', question_id)



def upload_lessons_from_sheet(lesson_spreadsheet_id, lesson_range, chapter_spreadsheet_id, chapter_range,
                              section_spreadsheet_id, section_range):
    lesson_data = get_sheet_data(lesson_spreadsheet_id, lesson_range)
    chapter_data = get_sheet_data(chapter_spreadsheet_id, chapter_range)
    section_data = get_sheet_data(section_spreadsheet_id, section_range)

    categories = [
        'Basic Theory',
        'Computer System',
        'Technology Element',
        'Development Technology',
        'Project Management',
        'Service Management',
        'Business Strategy',
        'System Strategy',
        'Corporate and Legal Affairs',
    ]

    for category in categories:
        Category.objects.get_or_create(name=category)

    if not lesson_data or not chapter_data or not section_data:
        print("Missing data from one or more sheets.")
        return

    lessons = {}
    chapters = {}

    for row in lesson_data[1:]:  # Skip header row
        lesson_id, lesson_name, is_locked = row
        lesson, created = Lesson.objects.update_or_create(
            id=lesson_id,
            defaults={
                'name': lesson_name,
                'is_locked': bool(int(is_locked))
            }
        )
        lessons[lesson_id] = lesson

    for row in chapter_data[1:]:  # Skip header row
        chapter_id, lesson_id, chapter_number, chapter_name, chapter_is_locked, is_main_chapter = row
        lesson = lessons.get(lesson_id)
        if lesson:
            chapter, created = Chapter.objects.update_or_create(
                id=chapter_id,
                lesson=lesson,
                defaults={
                    'name': chapter_name,
                    'number': chapter_number,
                    'is_locked': bool(int(chapter_is_locked)),
                    'is_main_chapter': bool(int(is_main_chapter))
                }
            )
            chapters[chapter_id] = chapter

    for row in section_data[1:]:
        section_id, chapter_id, section_number, section_name, content = row
        chapter = chapters.get(chapter_id)
        if chapter:
            section, updated = Section.objects.update_or_create(
                id=section_id,
                chapter=chapter,
                number=section_number,
                defaults={
                    'name': section_name,
                    'content': content
                }
            )

        print(
            f"Uploaded: {chapter.lesson.name} -> {chapter.number}. {chapter.name} -> Section {section_number}: {section_name}")
