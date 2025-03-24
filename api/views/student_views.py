from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
import random
from django.utils import timezone
from ..models import User, Question, Assessment, Answer, AssessmentResult, UserAbility, Category, Lesson, \
    LessonProgress, Class, AssessmentProgress, Chapter
from collections import defaultdict
from ..ai.estimate_student_ability import estimate_ability_irt
from django.shortcuts import get_object_or_404
from ..decorators import auth_required


@api_view(['GET'])
@auth_required("student")
def get_class(request):
    user: User = request.user
    # Get the classes the student is enrolled in
    if user.enrolled_class is None:
        return Response({"message": "You are not enrolled in any class."}, status=status.HTTP_200_OK)

    lessons = Lesson.objects.all()
    lesson_data = []

    for lesson in lessons:
        # Skip progress calculation if the lesson is locked
        if lesson.is_locked:
            lesson_data.append({
                "id": lesson.id,
                "lesson_name": lesson.lesson_name,
                "progress_percentage": None,  # No progress shown for locked lessons
                "current_chapter": None,
                "current_part": None,
                "is_locked": True
            })
            continue  # Skip to the next lesson

        progress = LessonProgress.objects.filter(user=user, lesson=lesson).first()

        if not progress:
            progress = LessonProgress(user=user, lesson=lesson)

        # Get total number of chapters in the lesson
        total_chapters = lesson.chapters.count()

        # Calculate progress percentage
        if progress.current_chapter:
            completed_chapters = progress.current_chapter.chapter_number
            progress_percentage = (completed_chapters / total_chapters) * 100 if total_chapters > 0 else 0.0
        else:
            progress_percentage = 0.0  # Default to 0% if no progress

        lesson_data.append({
            "id": lesson.id,
            "lesson_name": lesson.lesson_name,
            "progress_percentage": progress_percentage,
            "current_chapter": progress.current_chapter.chapter_name if progress.current_chapter else None,
            "current_part": progress.current_part.title if progress.current_part else None,
            "is_locked": False
        })

    class_obj = user.enrolled_class

    # Serialize class data
    class_data = {
        "id": class_obj.id,
        "name": class_obj.name,
        "teacher": class_obj.teacher.full_name,
        "class_code": class_obj.class_code,
        "lessons": lesson_data
    }

    return Response(class_data, status=status.HTTP_200_OK)


@api_view(['POST'])
@auth_required("student")
def join_class(request):
    user: User = request.user

    if user.enrolled_class is not None:
        return Response({'error': 'You are already enrolled in a class. You cannot join another.'},
                        status=status.HTTP_400_BAD_REQUEST)

    data = request.data
    code = data.get('class_code')

    if not code:
        return Response({'error': 'Class code is required.'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        class_instance = Class.objects.get(class_code=code)  # Fetch class with the given code
    except Class.DoesNotExist:
        return Response({'error': 'Class does not exist.'}, status=status.HTTP_404_NOT_FOUND)

    user.enrolled_class = class_instance
    user.save()

    return Response({'message': 'Successfully joined the class.'}, status=status.HTTP_200_OK)


@api_view(['GET'])
@auth_required("student")
def get_initial_exam(request):
    user: User = request.user

    print("Request User", request.user)

    if user.enrolled_class is None:
        return Response({"error": "Student is not enrolled to a class"}, status=status.HTTP_403_FORBIDDEN)

    # Retrieve the exam object; ensure that the exam belongs to the authenticated user
    exam = get_object_or_404(Assessment, class_owner=user.enrolled_class, is_initial=True)

    exam_data = {
        'exam_id': exam.id,
        'is_open': exam.deadline is not None,
    }

    if exam.deadline:
        exam_data['deadline'] = exam.deadline

    return Response(exam_data, status=status.HTTP_200_OK)


@api_view(['GET'])
@auth_required("student")
def initial_exam_taken(request):
    user: User = request.user

    if user.enrolled_class is None:
        return Response({"error": "Student is not enrolled to a class"}, status=status.HTTP_403_FORBIDDEN)

    # Retrieve the exam object; ensure that the exam belongs to the authenticated user
    exam = get_object_or_404(Assessment, class_owner=user.enrolled_class, is_initial=True)

    exam_result = AssessmentResult.objects.filter(exam=exam, user=user)

    return Response({"taken": exam_result.exists()}, status=status.HTTP_200_OK)


@api_view(['GET'])
@auth_required("student")
def take_initial_exam(request):
    user: User = request.user

    exam = Assessment.objects.filter(class_owner=user.enrolled_class, is_initial=True).first()

    if exam is None:
        return Response({"error": "Can't find initial exam"}, status=status.HTTP_404_NOT_FOUND)

    if exam.deadline is None:
        return Response({'error': 'Exam is not open.'}, status=status.HTTP_400_BAD_REQUEST)

    if exam.deadline and exam.deadline < timezone.now():
        return Response({'error': 'The deadline for this assessment has already passed.'},
                        status=status.HTTP_400_BAD_REQUEST)

    # Format the questions and answers to send back to the frontend
    exam_data = {
        'exam_id': exam.id,
        'no_of_items': exam.questions.count(),
        'time_limit': exam.time_limit,
        'questions': [
            {
                'question_id': question.id,
                'image_url': question.image_url,
                'question_text': question.question_text,
                'choices': list(question.choices.values()),
            }
            for question in exam.questions.all()
        ],
        'question_ids': [question.id for question in exam.questions.all()],
    }

    AssessmentProgress.objects.get_or_create(
        assessment=exam,
        user=user,
        defaults={'start_time': timezone.now()}
    )

    return Response(exam_data, status=status.HTTP_200_OK)


@api_view(['GET'])
@auth_required("student")
def take_exam(request):
    user: User = request.user

    # Get all questions from the database
    all_questions = Question.objects.all()

    if not all_questions:
        return Response({'error': 'No questions available to generate an exam.'}, status=status.HTTP_404_NOT_FOUND)

    selected_questions = random.sample(list(all_questions), 1)

    # Create a new exam instance for the authenticated user
    exam = Assessment.objects.create(
        created_by=user,
        type='Exam',
        source='student_initiated',
    )

    categories = set()
    for question in selected_questions:
        category = Category.objects.get(id=question.category_id)
        categories.add(category)

    exam.selected_categories.set(categories)
    exam.questions.set(selected_questions)
    exam.time_limit = 90 * len(selected_questions)
    exam.save()

    if exam.deadline is not None:
        AssessmentProgress.objects.create(assessment=exam, user=user)

    # Format the questions and answers to send back to the frontend
    exam_data = {
        'exam_id': exam.id,
        'time_limit': exam.time_limit,
        'questions': [
            {
                'question_id': question.id,
                'image_url': question.image_url,
                'question_text': question.question_text,
                'choices': list(question.choices.values()),
            }
            for question in selected_questions
        ],
        'question_ids': [question.id for question in selected_questions],
    }

    return Response(exam_data, status=status.HTTP_200_OK)


@api_view(['GET'])
@auth_required("student")
def check_time_limit(request, assessment_id):
    user: User = request.user
    progress = get_object_or_404(AssessmentProgress, user=user, assessment_id=assessment_id)

    # Ensure assessment has a time limit field
    if not hasattr(progress.assessment, 'time_limit'):
        return Response({"error": "Assessment time limit not found"}, status=status.HTTP_400_BAD_REQUEST)

    elapsed_time = (timezone.now() - progress.start_time).total_seconds()
    total_time_allowed = progress.assessment.time_limit
    time_left = max(0, total_time_allowed - elapsed_time)

    return Response({"time_left": int(time_left)}, status=status.HTTP_200_OK)


@api_view(['POST'])
@auth_required("student")
def submit_assessment(request, assessment_id):
    user: User = request.user

    # Retrieve the exam object
    assessment = get_object_or_404(Assessment, id=assessment_id)

    if assessment.deadline:
        assessment_progress = AssessmentProgress.objects.filter(user=user, assessment=assessment).first()
        time_elapsed = (timezone.now() - assessment_progress.start_time).total_seconds()

        is_auto_submission = time_elapsed >= assessment.time_limit if assessment.time_limit else False

        if not is_auto_submission:
            # Prevent manual submission after the deadline
            if assessment.deadline and assessment.deadline < timezone.now():
                return Response({'error': 'The deadline for this assessment has already passed.'},
                                status=status.HTTP_400_BAD_REQUEST)
        # else:
        #     # Allow auto-submission even if it's slightly past the deadline
        #     if assessment.deadline and assessment.deadline + timedelta(minutes=2) < timezone.now():
        #         return Response({'error': 'Auto-submission failed due to excessive delay.'},
        #                         status=status.HTTP_400_BAD_REQUEST)

    # Check if exam was already taken
    if AssessmentResult.objects.filter(assessment=assessment, user=user).exists():
        return Response({'error': 'Exam was already taken.'}, status=status.HTTP_400_BAD_REQUEST)

    data = request.data
    answers = data.get('answers', [])

    if not answers:
        return Response({'error': 'No answers provided.'}, status=status.HTTP_400_BAD_REQUEST)

    # Create an assessment result
    assessment_result = AssessmentResult.objects.create(
        assessment=assessment,
        score=0,
        time_taken=0,
        user=user
    )

    assessment_questions = {q.id: q for q in assessment.questions.all()}

    answers_to_create = []
    score = 0

    for question in assessment_questions.values():
        answer_data = next((a for a in answers if a["question_id"] == question.id), None)

        if answer_data:
            chosen_answer = answer_data.get('answer')
            time_spent = answer_data.get('time_spent', 0)
            correct_answer = question.choices[question.correct_answer]

            is_correct = chosen_answer == correct_answer
            if is_correct:
                score += 1

            answers_to_create.append(Answer(
                assessment_result=assessment_result,
                question=question,
                time_spent=time_spent,
                chosen_answer=chosen_answer,
                is_correct=is_correct
            ))

    Answer.objects.bulk_create(answers_to_create)

    assessment_result.score = score
    assessment_result.time_taken = data.get('total_time_taken_seconds', 0)
    assessment_result.save()

    return Response({'message': 'Exam submitted successfully.'}, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@auth_required("student")
def get_exam_results(request, assessment_id):
    user: User = request.user

    # Retrieve the exam object; ensure that the exam belongs to the authenticated user
    exam = get_object_or_404(Assessment, id=assessment_id)
    exam_results = get_object_or_404(AssessmentResult, assessment=exam, user=user)
    answers = Answer.objects.filter(assessment_result=exam_results)

    overall_correct_answers = 0
    overall_wrong_answers = 0
    category_stats = defaultdict(lambda: {'total_questions': 0, 'correct_answers': 0, 'wrong_answers': 0})

    # Serialize answers
    serialized_answers = []
    for answer in answers:
        category_name = answer.question.category.name
        category_stats[category_name]['total_questions'] += 1

        if answer.is_correct:
            category_stats[category_name]['correct_answers'] += 1
            overall_correct_answers += 1
        else:
            category_stats[category_name]['wrong_answers'] += 1
            overall_wrong_answers += 1

        serialized_answers.append({
            'question_id': answer.question.id,
            'question_text': answer.question.question_text,
            'choices': list(answer.question.choices.values()),
            'correct_answer': answer.question.choices[answer.question.correct_answer],
            'chosen_answer': answer.chosen_answer,
            'is_correct': answer.is_correct,
            'time_spent': answer.time_spent,
        })

    categories = [
        {
            'category_name': category_name,
            'total_questions': stats['total_questions'],
            'correct_answers': stats['correct_answers'],
            'wrong_answers': stats['wrong_answers'],
        }
        for category_name, stats in category_stats.items()
    ]

    result_data = {
        'exam_id': exam.id,
        'student_id': exam_results.user.id,
        'total_time_taken_seconds': exam_results.time_taken,
        'score': exam_results.score,
        'categories': categories,
        'overall_correct_answers': overall_correct_answers,
        'overall_wrong_answers': overall_wrong_answers,
        'total_questions': len(exam.questions.all()),
        'answers': serialized_answers,
    }

    return Response(result_data, status=status.HTTP_200_OK)


@api_view(['GET'])
@auth_required("student")
def get_ability(request):
    user: User = request.user

    estimate_ability_irt(user.id)

    # Retrieve stored abilities
    user_abilities = UserAbility.objects.filter(user_id=user.id)
    stored_abilities = {
        user_ability.category.name: user_ability.ability_level for user_ability in user_abilities
    }

    return Response({
        "abilities": stored_abilities,
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@auth_required("student")
def create_student_quiz(request):
    user: User = request.user
    print(request.data)

    selected_categories = request.data.get('selected_categories', [])
    selected_categories = [int(cat) for cat in selected_categories] if selected_categories else []

    print(selected_categories)

    no_of_questions = int(request.data.get('no_of_questions', 5))
    question_source = request.data.get('question_source')

    if question_source == 'previous_exam':
        all_questions = Question.objects.filter(category_id__in=selected_categories)

        if all_questions.count() < no_of_questions:
            return Response({'error': 'No questions available to generate an exam.'}, status=status.HTTP_404_NOT_FOUND)

        selected_questions = random.sample(list(all_questions), no_of_questions)

    elif question_source == 'ai_generated':
        return Response({'message': 'AI-generated questions feature has not been implemented yet.'},
                        status=status.HTTP_501_NOT_IMPLEMENTED)

    else:
        return Response({'message': 'AI-generated questions feature has not been implemented yet.'},
                        status=status.HTTP_501_NOT_IMPLEMENTED)

    categories = Category.objects.filter(id__in=selected_categories)

    quiz = Assessment.objects.create(
        created_by=user,
        type='Quiz',
        question_source=question_source,
        source='student_initiated'
    )

    quiz.questions.set(selected_questions)
    quiz.selected_categories.set(categories)
    quiz.save()

    quiz_data = {
        'quiz_id': quiz.id,
        'questions': [
            {
                'question_id': question.id,
                'image_url': question.image_url,
                'question_text': question.question_text,
                'choices': list(question.choices.values()),
            }
            for question in selected_questions
        ]
    }

    return Response(quiz_data, status=status.HTTP_200_OK)


@api_view(['POST'])
@auth_required("student")
def take_lesson_quiz(request):
    user: User = request.user
    data = request.data

    lesson_name = data.get('lesson')
    no_of_questions = data.get('no_of_questions')

    lesson = get_object_or_404(Lesson, lesson_name=lesson_name)
    lesson_category = get_object_or_404(Category, name=lesson_name)

    all_questions = list(Question.objects.filter(category_id=lesson_category.id))

    if len(all_questions) < no_of_questions:
        return Response({'error': 'Not enough questions available to generate an exam.'},
                        status=status.HTTP_404_NOT_FOUND)

    selected_questions = random.sample(list(all_questions), no_of_questions)

    lesson_quiz = Assessment.objects.create(
        lesson=lesson,
        created_by=user,
        type='Quiz',
        question_source='previous_exam',
        source='lesson',
    )

    lesson_quiz.selected_categories.set([lesson_category.id])
    lesson_quiz.questions.set(selected_questions)

    # Format the questions and answers to send back to the frontend
    quiz_data = {
        'quiz_id': lesson_quiz.id,
        'questions': [
            {
                'question_id': question.id,
                'image_url': question.image_url,
                'question_text': question.question_text,
                'choices': question.choices
            }
            for question in selected_questions
        ]
    }

    return Response(quiz_data, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@auth_required("student")
def get_class_assessments(request):
    user: User = request.user

    class_owner = Class.objects.get(id=user.enrolled_class.id)
    assessments = Assessment.objects.filter(class_owner=class_owner).order_by('-created_at')
    assessments_data = []

    for assessment in assessments:
        was_taken = AssessmentResult.objects.filter(assessment=assessment, user=user).exists()
        is_open = assessment.deadline is None or assessment.deadline >= timezone.now()
        in_progress = AssessmentProgress.objects.filter(assessment=assessment, user=user).exists()

        if was_taken:
            assessment_status = 'Completed'
        elif in_progress:
            assessment_status = 'In progress'
        else:
            assessment_status = 'Not Started'

        data = {
            'id': assessment.id,
            'name': assessment.name,
            'type': assessment.type,
            'items': assessment.questions.count(),
            'is_open': is_open,
            'status': assessment_status
        }

        if assessment.deadline:
            data.update({'deadline': assessment.deadline})

        assessments_data.append(data)

    return Response(assessments_data, status=status.HTTP_200_OK)


@api_view(['GET'])
@auth_required("student")
def get_history(request):
    user: User = request.user
    assessment_results = AssessmentResult.objects.filter(user_id=user.id)

    history = []
    for result in assessment_results:
        selected_categories = result.assessment.selected_categories.all()
        categories = []

        print(selected_categories)

        for category in selected_categories:
            # Get answers related to the category
            answers = Answer.objects.filter(
                assessment_result=result,
                question__category=category
            )

            correct_answers = answers.filter(is_correct=True).count()
            wrong_answers = answers.filter(is_correct=False).count()

            categories.append({
                'category_name': category.name,
                'correct_answer': correct_answers,
                'wrong_answer': wrong_answers
            })

        item = {
            'assessment_id': result.assessment.id,
            'type': result.assessment.type,
            'score': result.score,
            'total_items': result.assessment.questions.count(),
            'time_taken': result.time_taken,
            'date_taken': result.assessment.created_at,
            'question_source': result.assessment.question_source,
            'source': result.assessment.source,
            'categories': categories,
        }
        history.append(item)

    return Response(history, status=status.HTTP_200_OK)


@api_view(['GET'])
@auth_required("student")
def get_lessons(request):
    user: User = request.user

    lessons = Lesson.objects.all()
    lesson_data = []

    for lesson in lessons:
        lesson_progress, _ = LessonProgress.objects.get_or_create(
            user=user,
            lesson=lesson,
            defaults={"progress_percentage": 0.0}
        )

        lesson_data.append({
            "id": lesson.id,
            "lesson_name": lesson.name,
            "is_locked": lesson.is_locked,
            "progress": {
                "current_chapter": lesson_progress.current_chapter.id if lesson_progress.current_chapter else None,
                "current_section": lesson_progress.current_section.id if lesson_progress.current_section else None,
                "progress_percentage": lesson_progress.progress_percentage
            }
        })

    return Response(lesson_data, status=status.HTTP_200_OK)


@api_view(['GET'])
@auth_required("student")
def get_lesson(request, lesson_id):
    user: User = request.user

    if user.enrolled_class is None:
        return Response({'error': 'You are not enrolled.'}, status=status.HTTP_400_BAD_REQUEST)

    lesson = get_object_or_404(Lesson, id=lesson_id)

    if lesson.is_locked:
        return Response(
            {'error': 'Lesson is currently locked. Please wait till the teacher opens it'},
            status=status.HTTP_403_FORBIDDEN
        )

    chapters = lesson.chapters.all().order_by("chapter_number")

    # Get lesson progress if the user is a student
    lesson_progress, _ = LessonProgress.objects.get_or_create(
        user=user,
        lesson=lesson,
        defaults={"progress_percentage": 0.0}
    )

    lesson_structure = []

    for chapter in chapters:

        is_chapter_completed = lesson_progress.current_chapter and chapter.chapter_number < lesson_progress.current_chapter.chapter_number

        chapter_data = {
            "id": chapter.id,
            "chapter_name": chapter.chapter_name,
            "chapter_number": chapter.chapter_number,
            "is_main_chapter": chapter.is_main_chapter,
            "is_locked": chapter.is_locked,
            "completed": is_chapter_completed,
            "sections": []
        }

        for section in chapter.sections.all():
            is_section_completed = lesson_progress.current_part and section.number < lesson_progress.current_part.part_number

            chapter_data["sections"].append({
                "id": section.id,
                "title": section.name,
                "part_number": section.number,
                "completed": is_section_completed
            })

        lesson_structure.append(chapter_data)

        # TODO: Check how to properly check if the quiz was completed

        # is_quiz_taken = AssessmentResult.objects.filter(assessment=lesson, user=user).exists()
        if chapter.is_main_chapter:
            lesson_structure.append({
                "type": "quiz",
                "title": f"Quiz for {chapter.chapter_name}",
                "completed": is_chapter_completed
            })

    # Add the final lesson quiz at the end
    lesson_structure.append({
        "type": "quiz",
        "title": "Final Lesson Quiz",
        "completed": lesson_progress.progress_percentage == 100.0  # Completed if progress is 100%
    })

    lesson_data = {
        "id": lesson.id,
        "lesson_name": lesson.name,
        "structure": lesson_structure,
        "progress": {
            "current_chapter": lesson_progress.current_chapter.id if lesson_progress.current_chapter else None,
            "current_part": lesson_progress.current_part.id if lesson_progress.current_part else None,
            "progress_percentage": lesson_progress.progress_percentage
        }
    }

    return Response(lesson_data, status=status.HTTP_200_OK)


@api_view(['GET'])
@auth_required("student")
def get_chapter(request, lesson_id, chapter_id):
    user: User = request.user
    return Response({'error': 'Chapter does not exist.'}, status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
@auth_required("student")
def update_lesson_progress(request, lesson_id):
    user: User = request.user
    lesson = get_object_or_404(Lesson, id=lesson_id)
    data = request.data
    chapter_id = data.get("chapter_id")

    if not chapter_id:
        return Response({'error': 'chapter_id is required.'}, status=status.HTTP_400_BAD_REQUEST)

    chapter = get_object_or_404(Chapter, id=chapter_id, lesson=lesson)

    # Get or create lesson progress
    lesson_progress, created = LessonProgress.objects.get_or_create(
        user=user,
        lesson=lesson,
        defaults={"progress_percentage": 0.0}
    )

    # Update progress
    lesson_progress.current_chapter = chapter

    # Calculate progress percentage
    total_chapters = lesson.chapters.count()
    progress_percentage = (chapter.number / total_chapters) * 100
    lesson_progress.progress_percentage = progress_percentage

    lesson_progress.save()

    return Response({
        "message": "Lesson progress updated successfully.",
        "progress": {
            "current_chapter": lesson_progress.current_chapter.id,
            "progress_percentage": lesson_progress.progress_percentage
        }
    }, status=status.HTTP_200_OK)
