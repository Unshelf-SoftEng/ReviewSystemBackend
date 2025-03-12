from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from api.models import Question, Category, Lesson, Chapter
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
            print("Length of Row: ", len(row))
            if len(row) < 2 or not row[0]:  # Ensure the row has a valid ID
                print("Skipping empty or incomplete row:", row)
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


def upload_lessons_from_sheet(spreadsheet_id, range_name):
    sheet_data = get_sheet_data(spreadsheet_id, range_name)
    if sheet_data:
        for row in sheet_data[1:]:

            if Lesson.objects.filter(lesson_name=row[0]).exists():
                lesson = Lesson.objects.get(lesson_name=row[0])
            else:
                lesson = Lesson.objects.create(lesson_name=row[0])

            chapter, created = Chapter.objects.update_or_create(
                lesson=lesson,
                chapter_name=row[2],
                chapter_number=row[1],
                content=row[3]
            )

            action = "Updated" if not created else "Uploaded"
            print(f"{action}: {lesson.lesson_name} - {chapter.chapter_name}")
