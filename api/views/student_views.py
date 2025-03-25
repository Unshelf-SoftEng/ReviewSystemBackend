from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
import random
from django.utils import timezone
from ..models import User, Question, Assessment, Answer, AssessmentResult, UserAbility, Category, Lesson, \
    LessonProgress, Class, AssessmentProgress, Chapter, Section
from collections import defaultdict
from ..ai.estimate_student_ability import estimate_ability_irt
from django.shortcuts import get_object_or_404
from ..decorators import auth_required



@api_view(['GET'])
@auth_required("student")
def get_class(request):
    user: User = request.user

    if user.enrolled_class is None:
        return Response({"message": "You are not enrolled in any class."}, status=status.HTTP_200_OK)

    lessons = Lesson.objects.all()
    lesson_data = []

    for lesson in lessons:
        if lesson.is_locked:
            lesson_data.append({
                "id": lesson.id,
                "lesson_name": lesson.name,
                "is_locked": True
            })
            continue

        progress = LessonProgress.objects.filter(user=user, lesson=lesson).first()

        if not progress:
            lesson_data.append({
                "id": lesson.id,
                "lesson_name": lesson.name,
                "progress_percentage": 0.0,
            })
        else:
            total_chapters = lesson.chapters.count()
            completed_chapters = progress.current_chapter.number
            print("Progress", total_chapters, completed_chapters)
            progress_percentage = (completed_chapters / total_chapters) * 100 if total_chapters > 0 else 0.0

            lesson_data.append({
                "id": lesson.id,
                "lesson_name": lesson.name,
                "progress_percentage": round(progress_percentage, 2),
                "current_chapter": progress.current_chapter.name if progress.current_chapter else None,
                "current_part": progress.current_section.name if progress.current_section else None,
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

    code = request.data.get('class_code')

    if not code:
        return Response({'error': 'Class code is required.'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        class_obj = Class.objects.get(class_code=code)
    except Class.DoesNotExist:
        return Response({'error': 'Class does not exist.'}, status=status.HTTP_404_NOT_FOUND)

    user.enrolled_class = class_obj
    user.save()

    return Response({'message': 'Successfully joined the class.'}, status=status.HTTP_200_OK)


@api_view(['GET'])
@auth_required("student")
def get_initial_exam(request):
    user: User = request.user

    if user.enrolled_class is None:
        return Response({"error": "Student is not enrolled to a class"}, status=status.HTTP_403_FORBIDDEN)

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

    if user.enrolled_class:
        exists = AssessmentResult.objects.filter(
            assessment__class_owner=user.enrolled_class,
            assessment__is_initial=True
        ).exists()

        return Response({'taken': exists}, status=status.HTTP_200_OK)
    else:
        return Response({"error": "Student is not enrolled to a class"}, status=status.HTTP_403_FORBIDDEN)


@api_view(['GET'])
@auth_required("student")
def take_initial_exam(request):
    user: User = request.user

    exam = Assessment.objects.filter(
        class_owner=user.enrolled_class, is_initial=True
    ).prefetch_related("questions").only("id", "time_limit", "deadline").first()

    if not exam:
        return Response({"error": "Can't find initial exam"}, status=status.HTTP_404_NOT_FOUND)

    if not exam.deadline or exam.deadline < timezone.now():
        return Response({'error': 'Exam is not available.'}, status=status.HTTP_400_BAD_REQUEST)

    if AssessmentResult.objects.filter(assessment=exam, user=user).exists():
        return Response({'error': 'Student has already taken the exam.'}, status=status.HTTP_400_BAD_REQUEST)

    # Fetch questions only once to prevent multiple queries
    questions = list(exam.questions.all())

    exam_data = {
        'exam_id': exam.id,
        'no_of_items': len(questions),
        'time_limit': exam.time_limit,
        'questions': [
            {
                'question_id': question.id,
                'image_url': question.image_url,
                'question_text': question.question_text,
                'choices': question.choices if isinstance(question.choices, list) else list(question.choices.values()),
            }
            for question in questions
        ],
        'question_ids': [question.id for question in questions],
    }

    # Only create AssessmentProgress if it does NOT exist
    if not AssessmentProgress.objects.filter(assessment=exam, user=user).exists():
        AssessmentProgress.objects.create(
            assessment=exam,
            user=user,
            start_time=timezone.now()
        )

    return Response(exam_data, status=status.HTTP_200_OK)


@api_view(['GET'])
@auth_required("student")
def take_exam(request):
    no_of_items = 60
    user: User = request.user

    total_questions = Question.objects.count()

    if total_questions == 0:
        return Response({'error': 'No questions available to generate an exam.'}, status=status.HTTP_404_NOT_FOUND)

    num_to_fetch = min(no_of_items, total_questions)
    selected_questions = list(Question.objects.order_by('?')[:num_to_fetch])

    # Create the exam instance
    exam = Assessment.objects.create(
        created_by=user,
        type='Exam',
        source='student_initiated',
        time_limit=90 * num_to_fetch,
    )

    category_ids = set(selected_questions[i].category_id for i in range(len(selected_questions)))
    categories = Category.objects.filter(id__in=category_ids)

    exam.selected_categories.set(categories)
    exam.questions.set(selected_questions)

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

    assessment: Assessment = Assessment.objects.filter(id=assessment_id).first()

    if assessment.time_limit is None:
        return Response({'error': 'No time limit.'}, status=status.HTTP_404_NOT_FOUND)

    progress = get_object_or_404(AssessmentProgress, user=user, assessment_id=assessment_id)

    elapsed_time = (timezone.now() - progress.start_time).total_seconds()
    total_time_allowed = progress.assessment.time_limit
    time_left = total_time_allowed - elapsed_time

    if elapsed_time > total_time_allowed:
        return Response({'error': 'Time limit exceeded.'}, status=status.HTTP_400_BAD_REQUEST)

    return Response({"time_left": int(time_left)}, status=status.HTTP_200_OK)


@api_view(['POST'])
@auth_required("student")
def submit_assessment(request, assessment_id):
    user: User = request.user
    assessment = get_object_or_404(Assessment, id=assessment_id)

    if AssessmentResult.objects.filter(assessment=assessment, user=user).exists():
        return Response({'error': 'Exam was already taken.'}, status=status.HTTP_400_BAD_REQUEST)

    assessment_progress = AssessmentProgress.objects.filter(user=user, assessment=assessment).first()

    # Validate time limit and deadline
    if assessment.deadline or assessment.time_limit:
        now = timezone.now()
        if assessment_progress:
            time_elapsed = (now - assessment_progress.start_time).total_seconds()
            is_auto_submission = assessment.time_limit and time_elapsed >= assessment.time_limit
        else:
            time_elapsed = 0
            is_auto_submission = False

        if not is_auto_submission and assessment.deadline and now > assessment.deadline:
            return Response({'error': 'The deadline for this assessment has already passed.'},
                            status=status.HTTP_400_BAD_REQUEST)

    answers = request.data.get('answers', [])
    if not answers:
        return Response({'error': 'No answers provided.'}, status=status.HTTP_400_BAD_REQUEST)

    assessment_result = AssessmentResult.objects.create(
        assessment=assessment,
        user=user,
        score=0,
        time_taken=request.data.get('total_time_taken_seconds', 0)
    )

    assessment_questions = {q.id: q for q in assessment.questions.all()}
    answer_dict = {a["question_id"]: a for a in answers}

    answers_to_create = []
    score = 0

    for question_id, question in assessment_questions.items():
        answer_data = answer_dict.get(question_id)
        if answer_data:
            chosen_answer = answer_data.get('answer')
            time_spent = answer_data.get('time_spent', 0)
            correct_answer = question.choices[question.correct_answer]

            is_correct = chosen_answer == correct_answer
            score += int(is_correct)

            answers_to_create.append(Answer(
                assessment_result=assessment_result,
                question=question,
                time_spent=time_spent,
                chosen_answer=chosen_answer,
                is_correct=is_correct
            ))

    Answer.objects.bulk_create(answers_to_create)
    AssessmentResult.objects.filter(id=assessment_result.id).update(score=score)

    return Response({'message': 'Exam submitted successfully.'}, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@auth_required("student")
def get_assessment_result(request, assessment_id):
    user: User = request.user

    result = get_object_or_404(AssessmentResult.objects.prefetch_related(
        "answers__question__category"
    ), assessment__id=assessment_id, user=user)

    answers = list(result.answers.all())  # Fetch all answers in one query

    overall_correct_answers = 0
    overall_wrong_answers = 0
    category_stats = defaultdict(lambda: {'total_questions': 0, 'correct_answers': 0, 'wrong_answers': 0})

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
            'choices': answer.question.choices if isinstance(answer.question.choices, list) else list(answer.question.choices.values()),
            'correct_answer': answer.question.choices[answer.question.correct_answer],
            'chosen_answer': answer.chosen_answer,
            'is_correct': answer.is_correct,
            'time_spent': answer.time_spent,
        })

    categories = [
        {
            'category_name': category_name,
            **stats  # Expands 'total_questions', 'correct_answers', and 'wrong_answers'
        }
        for category_name, stats in category_stats.items()
    ]

    result_data = {
        'exam_id': result.assessment.id,
        'student_id': result.user.id,
        'total_time_taken_seconds': result.time_taken,
        'score': result.score,
        'categories': categories,
        'overall_correct_answers': overall_correct_answers,
        'overall_wrong_answers': overall_wrong_answers,
        'total_questions': result.assessment.questions.count(),  # Optimized counting
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

    selected_categories = request.data.get('selected_categories', [])
    selected_categories = [int(cat) for cat in selected_categories] if selected_categories else []
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

    lesson = get_object_or_404(Lesson, name=lesson_name)
    lesson_category = get_object_or_404(Category, name=lesson_name)

    all_questions = list(Question.objects.filter(category_id=lesson_category.id))
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

    assessments = Assessment.objects.filter(class_owner=user.enrolled_class).order_by('-created_at')
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


# @api_view(['GET'])
# @auth_required("student")
# def get_lessons(request):
#     user: User = request.user
#
#     lessons = Lesson.objects.all()
#     lesson_data = []
#
#     for lesson in lessons:
#         lesson_progress, _ = LessonProgress.objects.get_or_create(
#             user=user,
#             lesson=lesson,
#             defaults={"progress_percentage": 0.0}
#         )
#
#         lesson_data.append({
#             "id": lesson.id,
#             "lesson_name": lesson.name,
#             "is_locked": lesson.is_locked,
#             "progress": {
#                 "current_chapter": lesson_progress.current_chapter.id if lesson_progress.current_chapter else None,
#                 "current_section": lesson_progress.current_section.id if lesson_progress.current_section else None,
#                 "progress_percentage": lesson_progress.progress_percentage
#             }
#         })
#
#     return Response(lesson_data, status=status.HTTP_200_OK)


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

    chapters = lesson.chapters.all().order_by("number")
    first_chapter = lesson.chapters.first()
    first_section = first_chapter.sections.first()

    # Get lesson progress if the user is a student
    lesson_progress, _ = LessonProgress.objects.get_or_create(
        user=user,
        lesson=lesson,
        defaults={
            "current_chapter": first_chapter,
            "current_section": first_section,
        }
    )
    lesson_structure = []

    for chapter in chapters:

        chapter_data = {
            "id": chapter.id,
            "chapter_number": chapter.number,
            "chapter_name": chapter.name,
            "is_main_chapter": chapter.is_main_chapter,
            "is_locked": chapter.is_locked,
        }

        if not chapter.is_locked:
            is_chapter_completed = chapter.number < lesson_progress.current_chapter.number

            chapter_data["completed"] = is_chapter_completed
            chapter_data["structure"] = []

            for section in chapter.sections.all():
                is_section_completed = (
                        lesson_progress.current_section is not None
                        and section.number < lesson_progress.current_section.number
                )

                chapter_data["structure"].append({
                    "section_id": section.id,
                    "section_number": section.number,
                    "section_name": section.name,
                    "completed": is_section_completed
                })

            if chapter.is_main_chapter:
                chapter_data["structure"].append({
                    "type": "quiz",
                    "title": f"Quiz for {chapter.name}",
                    "completed": AssessmentResult.objects.filter(assessment__chapter=chapter).exists()
                })

        lesson_structure.append(chapter_data)

    lesson_structure.append({
        "type": "quiz",
        "title": "Final Lesson Quiz",
        "completed": AssessmentResult.objects.filter(assessment__lesson=lesson).exists()
    })

    total_chapters = lesson.chapters.count()
    completed_chapters = lesson_progress.current_chapter.number
    progress_percentage = (completed_chapters / total_chapters) * 100 if total_chapters > 0 else 0.0

    lesson_data = {
        "id": lesson.id,
        "lesson_name": lesson.name,
        "structure": lesson_structure,
        "progress": {
            "current_chapter": lesson_progress.current_chapter.name,
            "current_section": lesson_progress.current_section.name if lesson_progress.current_section is not None else None,
            "progress_percentage": round(progress_percentage, 2)
        }
    }

    return Response(lesson_data, status=status.HTTP_200_OK)


@api_view(['GET'])
@auth_required("student")
def get_chapter(request, lesson_id, chapter_id):
    chapter = get_object_or_404(Chapter, id=chapter_id)

    if chapter.is_locked:
        return Response(
            {'error': 'Lesson is currently locked. Please wait till the teacher opens it'},
            status=status.HTTP_403_FORBIDDEN
        )

    section_data = []

    for section in chapter.sections.all():
        section_data.append({
            "id": section.id,
            "number": section.number,
            "title": section.name,
            "content": section.content,
        })

    chapter_data = {
        "id": chapter.id,
        "chapter_number": chapter.number,
        "chapter_name": chapter.name,
        "sections": section_data
    }

    return Response(chapter_data, status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
@auth_required("student")
def update_lesson_progress(request, lesson_id):
    user: User = request.user
    lesson = get_object_or_404(Lesson, id=lesson_id)
    data = request.data

    chapter_id = data.get("chapter_id")
    section_id = data.get("section_id")

    chapter = get_object_or_404(Chapter, lesson=lesson, number=chapter_id)
    section = get_object_or_404(Section, id=section_id, chapter=chapter)

    # Get or create lesson progress
    lesson_progress, _ = LessonProgress.objects.get_or_create(
        user=user,
        lesson=lesson,
        defaults={"current_chapter": chapter, "current_section": section}
    )

    lesson_progress.current_chapter = chapter
    if section:
        lesson_progress.current_section = section
    lesson_progress.save()

    return Response({"message": "Lesson progress updated successfully."}, status=status.HTTP_200_OK)
