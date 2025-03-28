from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
import random
from django.utils import timezone
from api.models import User, Question, Assessment, Answer, AssessmentResult, UserAbility, Category, Lesson, \
    LessonProgress, Class, AssessmentProgress, Chapter, Section
from collections import defaultdict
from api.ai.estimate_student_ability import estimate_ability_irt, estimate_ability_elo
from django.shortcuts import get_object_or_404
from api.decorators import auth_required
from datetime import timedelta


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
    ).select_related("class_owner").prefetch_related("questions").only("id", "time_limit", "deadline",
                                                                       "class_owner").first()
    if user.enrolled_class is None:
        return Response({'error': "You are not enrolled in any class"}, status=status.HTTP_403_FORBIDDEN
        )

    if not exam:
        return Response({"error": "Can't find initial exam"}, status=status.HTTP_404_NOT_FOUND)

    if not exam.deadline:
        return Response({'error': 'Exam is not yet open'}, status=status.HTTP_400_BAD_REQUEST)

    if exam.deadline < timezone.now():
        return Response({'error': 'Exam deadline has already passed'}, status=status.HTTP_400_BAD_REQUEST)

    progress, created = AssessmentProgress.objects.get_or_create(
        assessment=exam, user=user,
        defaults={"start_time": timezone.now()}
    )

    end_time = progress.start_time + timedelta(seconds=exam.time_limit)
    remaining_time = (end_time - timezone.now()).total_seconds()

    if remaining_time <= 0:
        return Response({'error': 'Time limit has exceeded'}, status=status.HTTP_400_BAD_REQUEST)

    if AssessmentResult.objects.filter(assessment=exam, user=user).exists():
        return Response({'error': 'Student has already taken the exam.'}, status=status.HTTP_400_BAD_REQUEST)

    questions = list(exam.questions.values("id", "image_url", "question_text", "choices"))

    exam_data = {
        'exam_id': exam.id,
        'no_of_items': len(questions),
        'time_limit': int(remaining_time),
        'questions': [
            {
                'question_id': question["id"],
                'image_url': question["image_url"],
                'question_text': question["question_text"],
                'choices': question["choices"] if isinstance(question["choices"], list) else list(
                    question["choices"].values()),
            }
            for question in questions
        ],
        'question_ids': [q["id"] for q in questions],
    }

    return Response(exam_data, status=status.HTTP_200_OK)


@api_view(['GET'])
@auth_required("student")
def take_exam(request):
    no_of_items = 60
    user: User = request.user

    total_questions = Question.objects.count()

    if total_questions == 0:
        return Response({'error': 'No questions available to generate an exam.'}, status=status.HTTP_404_NOT_FOUND)

    selected_questions = list(Question.objects.order_by('?')[no_of_items:])

    exam = Assessment.objects.create(
        created_by=user,
        type='exam',
        source='student_initiated',
        time_limit=90 * no_of_items,
    )

    category_ids = set(selected_questions[i].category_id for i in range(len(selected_questions)))
    categories = Category.objects.filter(id__in=category_ids)

    exam.selected_categories.set(categories)
    exam.questions.set(selected_questions)

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


@api_view(['POST'])
@auth_required("student")
def take_quiz(request):
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
        type='quiz',
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


@api_view(['GET'])
@auth_required("student")
def take_lesson_assessment(request, lesson_id):
    user: User = request.user
    data = request.data

    no_of_questions = 20

    lesson = get_object_or_404(Lesson, id=lesson_id)
    lesson_category = get_object_or_404(Category, name=lesson.name)

    all_questions = list(Question.objects.filter(category_id=lesson_category.id))
    selected_questions = random.sample(list(all_questions), no_of_questions)

    lesson_assessment = Assessment.objects.create(
        name=f'Lesson Quiz: {lesson.name}',
        lesson=lesson,
        class_owner=user.enrolled_class,
        type='quiz',
        question_source='previous_exam',
        source='lesson_generated',
    )

    lesson_assessment.selected_categories.set([lesson_category.id])
    lesson_assessment.questions.set(selected_questions)

    quiz_data = {
        'quiz_id': lesson_assessment.id,
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
def take_chapter_assessment(request, chapter_id):
    user: User = request.user

    no_of_questions = 20

    chapter = Chapter.objects.get(id=chapter_id)

    if chapter is None:
        return Response({'error': 'Chapter does not exist.'}, status=status.HTTP_404_NOT_FOUND)

    all_questions = list(Question.objects.filter(category__subcategory__name=chapter.name))
    selected_questions = random.sample(list(all_questions), no_of_questions)

    chapter_assessment = Assessment.objects.create(
        name=f'Chapter Quiz: {chapter.name}',
        chapter=chapter,
        class_owner=user.enrolled_class,
        type='quiz',
        question_source='previous_exam',
        source='chapter_generated',
    )

    chapter_assessment.selected_categories.set([chapter.lesson.id])
    chapter_assessment.questions.set(selected_questions)

    quiz_data = {
        'quiz_id': chapter_assessment.id,
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
def take_teacher_assessment(request, assessment_id):
    user: User = request.user

    assessment = Assessment.objects.filter(assessment__id=assessment_id)

    if user.enrolled_class != assessment.class_owner:
        return Response({'error': "User doesn't belong to the class"}, status=status.HTTP_403_FORBIDDEN)

    quiz_data = {
        'quiz_id': assessment.id,
        'deadline': assessment.deadline,
        'type': assessment.type,
        'questions': [
            {
                'question_id': question.id,
                'image_url': question.image_url,
                'question_text': question.question_text,
                'choices': question.choices
            }
            for question in assessment.questions
        ]
    }

    return Response(quiz_data, status=status.HTTP_200_OK)


@api_view(['GET'])
@auth_required("student")
def check_time_limit(request, assessment_id):
    user: User = request.user

    assessment: Assessment = Assessment.objects.filter(id=assessment_id).first()

    if assessment is None:
        return Response({'error': 'Assessment does not exist'}, status=status.HTTP_404_NOT_FOUND)

    if assessment.time_limit is None:
        return Response({'error': 'No time limit.'}, status=status.HTTP_404_NOT_FOUND)

    progress = AssessmentProgress.objects.filter(user=user, assessment_id=assessment_id).first()

    if progress is None:
        return Response({'error': "No progress found for this assessment."}, status=status.HTTP_404_NOT_FOUND)

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
    assessment = Assessment.objects.filter(id=assessment_id).first()
    current_time = timezone.now()

    if assessment is None:
        return Response({'error': 'Assessment does not exist'}, status=status.HTTP_404_NOT_FOUND)

    if assessment.source == 'student_generated' and assessment.created_by != user:
        return Response({'error': 'You are not allowed to submit answers on this assessment'},
                        status=status.HTTP_403_FORBIDDEN)
    else:
        if assessment.class_owner != user.enrolled_class:
            return Response({'error': 'You are not allowed to submit answers on this assessment'},
                            status=status.HTTP_403_FORBIDDEN)

    if AssessmentResult.objects.filter(assessment=assessment, user=user).exists():
        return Response({'error': 'Exam was already taken.'}, status=status.HTTP_400_BAD_REQUEST)

    assessment_progress = AssessmentProgress.objects.filter(user=user, assessment_id=assessment_id).first()

    if assessment.deadline or assessment.time_limit:
        if assessment_progress:
            time_elapsed = (current_time - assessment_progress.start_time).total_seconds()
            is_auto_submission = assessment.time_limit and time_elapsed >= assessment.time_limit
        else:
            is_auto_submission = False

        if not is_auto_submission and assessment.deadline and current_time > assessment.deadline:
            return Response({'error': 'The deadline for this assessment has already passed.'},
                            status=status.HTTP_400_BAD_REQUEST)

    answers = request.data.get('answers', [])

    if not answers:
        return Response({'error': 'No answers provided.'}, status=status.HTTP_400_BAD_REQUEST)

    assessment_result = AssessmentResult.objects.create(
        assessment=assessment,
        user=user,
        score=0,
        created_at=current_time
    )

    if assessment_progress:
        assessment_result.time_taken = (current_time - assessment_progress.start_time).seconds
        assessment_result.save()

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

    return Response({'message': 'Assessment was submitted successfully'}, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@auth_required("student")
def get_assessment_result(request, assessment_id):
    user: User = request.user

    result = AssessmentResult.objects.prefetch_related("answers__question__category").filter(
        assessment__id=assessment_id, user=user).first()

    if result is None:
        return Response({'error': 'No Result for Assessment Found'}, status=status.HTTP_404_NOT_FOUND)

    answers = list(result.answers.all())

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
            'choices': answer.question.choices if isinstance(answer.question.choices, list) else list(
                answer.question.choices.values()),
            'chosen_answer': answer.chosen_answer,
            'is_correct': answer.is_correct,
            'time_spent': answer.time_spent,
        })

    categories = [
        {
            'category_name': category_name,
            **stats
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
    estimate_ability_elo(user.id)

    # Retrieve stored abilities
    user_abilities = UserAbility.objects.filter(user_id=user.id)
    irt_abilities = {
        user_ability.category.name: user_ability.irt_ability for user_ability in user_abilities
    }

    elo_abilities = {
        user_ability.category.name: user_ability.elo_ability for user_ability in user_abilities
    }

    return Response({
        "abilities": irt_abilities,
        "elo_abilities": elo_abilities
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@auth_required("student")
def get_class_assessments(request):
    user: User = request.user

    assessments = Assessment.objects.filter(source='teacher_generated', class_owner=user.enrolled_class).order_by(
        '-created_at')
    assessments_data = []

    for assessment in assessments:
        was_taken = AssessmentResult.objects.filter(assessment=assessment, user=user).exists()
        is_open = assessment.deadline is None or assessment.deadline >= timezone.now()
        in_progress = AssessmentProgress.objects.filter(assessment=assessment, user=user).exists()

        if was_taken:
            assessment_status = 'Completed'
        elif in_progress:
            assessment_status = 'In Progress'
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
    assessment_results = AssessmentResult.objects.filter(user__id=user.id).order_by('-created_at')

    history = []
    for result in assessment_results:
        selected_categories = result.assessment.selected_categories.all()
        categories = []

        for category in selected_categories:
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
        "title": f"Quiz for {lesson.name}",
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
