from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
import random
from django.db.models import Prefetch
from django.utils import timezone
from api.models import User, Question, Assessment, Answer, AssessmentResult, UserAbility, Category, Lesson, \
    LessonProgress, Class, Chapter, Section
from collections import defaultdict
from api.ai.estimate_student_ability import estimate_ability_irt, estimate_ability_elo
from django.shortcuts import get_object_or_404
from api.decorators import auth_required
from datetime import timedelta
from django.utils.timezone import now

AUTO_SUBMISSION_GRACE_PERIOD = 30


@api_view(['GET'])
@auth_required("student")
def joined_class(request):
    user: User = request.user

    response_data = {
        'joined': user.enrolled_class is not None
    }

    return Response(response_data, status=status.HTTP_200_OK)


@api_view(["GET"])
@auth_required("student")
def get_class(request):
    user: User = request.user

    if not user.enrolled_class:
        return Response({"error": "Student is not enrolled in a class."}, status=status.HTTP_200_OK)

    class_obj = user.enrolled_class
    lessons = Lesson.objects.only("id", "name", "is_locked")

    lesson_data = [
        {
            "id": lesson.id,
            "lesson_name": lesson.name,
            "is_locked": lesson.is_locked,
        }
        for lesson in lessons
    ]

    class_data = {
        "id": class_obj.id,
        "student_name": user.full_name,
        "name": class_obj.name,
        "teacher": class_obj.teacher.full_name,
        "class_code": class_obj.class_code,
        "lessons": lesson_data,
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
        return Response({'error': 'Missing class code'}, status=status.HTTP_400_BAD_REQUEST)

    class_obj = Class.objects.filter(class_code=code).first()
    if not class_obj:
        return Response({'error': 'Invalid class code'}, status=status.HTTP_400_BAD_REQUEST)

    user.enrolled_class = class_obj
    user.save()

    return Response({'message': 'Successfully joined the class.'}, status=status.HTTP_200_OK)


@api_view(['GET'])
@auth_required("student")
def get_dashboard_data(request):
    user: User = request.user
    lessons = Lesson.objects.only("id", "name", "is_locked")

    lesson_data = [
        {
            "id": lesson.id,
            "lesson_name": lesson.name,
            "is_locked": lesson.is_locked,
        }
        for lesson in lessons
    ]

    assessment_results = AssessmentResult.objects.filter(user=user).order_by('-start_time')

    history_data = []
    for result in assessment_results:
        selected_categories = result.assessment.selected_categories.all()
        categories = []

        for category in selected_categories:
            total_questions = result.assessment.questions.filter(category=category).count()
            answered_questions = Answer.objects.filter(assessment_result=result, question__category=category)
            correct_count = answered_questions.filter(is_correct=True).count()

            categories.append({
                'category_name': category.name,
                'total_questions': total_questions,
                'correct_answer': correct_count,
            })

        item = {
            'assessment_id': result.assessment.id,
            'name': result.assessment.name,
            'type': result.assessment.type,
            'score': result.score or 0,
            'total_items': result.assessment.questions.count() or 0,
            'time_taken': result.time_taken or 0,
            'date_taken': result.assessment.created_at.isoformat() if result.assessment.created_at else None,
            'question_source': result.assessment.question_source,
            'source': result.assessment.source,
            'categories': categories,
            'is_initial_assessment': result.assessment.is_initial
        }
        history_data.append(item)

    response_data = {
        "student_name": user.full_name,
        "lessons": lesson_data,
        "history": history_data
    }

    return Response(response_data, status=status.HTTP_200_OK)


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

    if not user.enrolled_class:
        return Response({"error": "Student is not enrolled to a class"}, status=status.HTTP_403_FORBIDDEN)

    result = AssessmentResult.objects.filter(
        assessment__class_owner=user.enrolled_class,
        assessment__is_initial=True,
        user=user
    ).first()

    if not result:
        return Response({'status': 'not_taken'}, status=status.HTTP_200_OK)

    if result.is_submitted:
        return Response({'status': 'taken'}, status=status.HTTP_200_OK)

    current_time = timezone.now()
    time_limit_end = result.start_time + timedelta(seconds=result.assessment.time_limit)
    deadline = result.assessment.deadline

    if current_time >= time_limit_end or (deadline and current_time >= deadline):

        print('Was here')
        result.is_submitted = True
        result.save()
        return Response({'status': 'taken'}, status=status.HTTP_200_OK)
    else:
        return Response({'status': 'ongoing'}, status=status.HTTP_200_OK)


@api_view(['GET'])
@auth_required("student")
def take_initial_exam(request):
    user: User = request.user

    if user.enrolled_class is None:
        return Response({'error': "Student is not enrolled in any class"}, status=status.HTTP_403_FORBIDDEN)

    exam = Assessment.objects.filter(
        class_owner=user.enrolled_class,
        is_initial=True,
        is_active=True
    ).select_related("class_owner").prefetch_related("questions").only("id", "time_limit", "deadline",
                                                                       "class_owner").first()

    if not exam:
        return Response({"error": "Initial Exam doesn't exist"}, status=status.HTTP_404_NOT_FOUND)

    if not exam.deadline:
        return Response({'error': 'Initial Exam is not open'}, status=status.HTTP_400_BAD_REQUEST)

    current_time = timezone.now()

    if exam.deadline < current_time:
        return Response({'error': 'Initial Exam deadline has already passed'}, status=status.HTTP_400_BAD_REQUEST)

    result, created = AssessmentResult.objects.get_or_create(
        assessment=exam, user=user,
        defaults={"start_time": current_time}
    )

    expected_end_time = result.start_time + timedelta(seconds=exam.time_limit)
    end_time = min(expected_end_time, exam.deadline)
    remaining_time = (end_time - current_time).total_seconds()

    if remaining_time <= 0:
        return Response({'error': 'Time limit has exceeded'}, status=status.HTTP_400_BAD_REQUEST)

    if result.is_submitted:
        return Response({'error': 'Student has already taken the exam.'}, status=status.HTTP_400_BAD_REQUEST)

    questions_qs = exam.questions.all().values("id", "image_url", "question_text", "choices")
    questions_dict = {q["id"]: q for q in questions_qs}

    if not result.question_order:
        question_list = list(questions_dict.values())
        random.shuffle(question_list)
        result.question_order = [q["id"] for q in question_list]
        result.save()
    else:
        question_list = [questions_dict[qid] for qid in result.question_order if qid in questions_dict]

    answers = Answer.objects.filter(assessment_result=result)

    answers_dict = {
        answer.question_id: {
            'chosen_answer': answer.chosen_answer,
            'time_spent': answer.time_spent
        }
        for answer in answers
    }

    questions_data = []
    for question in question_list:
        question_data = {
            'question_id': question["id"],
            'image_url': question["image_url"],
            'question_text': question["question_text"],
            'choices': question["choices"] if isinstance(question["choices"], list)
            else list(question["choices"].values()),
        }

        answer_info = answers_dict.get(question["id"], {})
        if 'chosen_answer' in answer_info:
            question_data.update({
                'chosen_answer': answer_info['chosen_answer'],
                'time_spent': answer_info.get('time_spent', 0),
            })

        questions_data.append(question_data)

    exam_data = {
        'exam_id': exam.id,
        'no_of_items': len(question_list),
        'time_limit': int(remaining_time),
        'questions': questions_data,
        'question_ids': [q["id"] for q in question_list],
    }

    return Response(exam_data, status=status.HTTP_200_OK)


@api_view(['GET'])
@auth_required("student")
def check_time_limit(request, assessment_id):
    user: User = request.user

    assessment = get_object_or_404(Assessment, id=assessment_id, is_active=True)

    if assessment.time_limit is None:
        return Response({'error': 'No time limit.'}, status=status.HTTP_404_NOT_FOUND)

    result = AssessmentResult.objects.filter(user=user, assessment_id=assessment_id).first()

    if result is None:
        return Response({'error': "No progress found for this assessment."}, status=status.HTTP_404_NOT_FOUND)

    current_time = timezone.now()
    elapsed_time = (current_time - result.start_time).total_seconds()
    time_limit = result.assessment.time_limit
    deadline = result.assessment.deadline

    if deadline:
        remaining_time_until_deadline = (deadline - current_time).total_seconds()
    else:
        remaining_time_until_deadline = float('inf')

    remaining_time_based_on_limit = time_limit - elapsed_time

    remaining_time = min(remaining_time_based_on_limit, remaining_time_until_deadline)

    if remaining_time <= 0:
        return Response({'error': 'Time limit exceeded.'}, status=status.HTTP_404_NOT_FOUND)

    return Response({"time_left": int(remaining_time)}, status=status.HTTP_200_OK)


@api_view(['POST'])
@auth_required("student")
def save_progress(request, assessment_id):
    user: User = request.user
    answers = request.data.get('answers', [])

    if not answers:
        return Response({'error': 'No answers provided.'}, status=status.HTTP_400_BAD_REQUEST)

    current_time = timezone.now()

    result = get_object_or_404(AssessmentResult, user=user, assessment__id=assessment_id)

    if result.is_submitted:
        return Response({'error': 'Result was already submitted'}, status=status.HTTP_400_BAD_REQUEST)

    # Fetch all the questions upfront to avoid N+1 queries
    question_ids = [answer_data.get('question_id') for answer_data in answers]
    questions = {question.id: question for question in Question.objects.filter(id__in=question_ids)}

    # Prepare bulk update for existing answers and bulk create for new ones
    answers_to_update = []
    answers_to_create = []

    # Get existing answers
    existing_answers = Answer.objects.filter(assessment_result=result, question__id__in=question_ids)
    existing_answers_dict = {(answer.question.id): answer for answer in existing_answers}

    score = 0

    for answer_data in answers:
        question_id = answer_data.get('question_id')
        chosen_answer = answer_data.get('answer')
        time_spent = int(answer_data.get('time_spent', 0))

        question = questions.get(question_id)
        if question:
            existing_answer = existing_answers_dict.get(question_id)
            correct_answer = question.choices[question.correct_answer]
            is_correct = chosen_answer == correct_answer
            score += is_correct

            if existing_answer:
                existing_answer.chosen_answer = chosen_answer
                existing_answer.time_spent = time_spent
                existing_answer.is_correct = is_correct
                answers_to_update.append(existing_answer)

            else:
                # If the answer doesn't exist, create a new one
                answers_to_create.append(
                    Answer(
                        assessment_result=result,
                        question=question,
                        chosen_answer=chosen_answer,
                        time_spent=time_spent,
                        is_correct=is_correct
                    )
                )

    # Bulk update existing answers
    if answers_to_update:
        Answer.objects.bulk_update(answers_to_update, ['chosen_answer', 'time_spent'])

    # Bulk create new answers
    if answers_to_create:
        Answer.objects.bulk_create(answers_to_create)

    response_data = {
        'message': 'Progress was stored successfully',
    }

    if result.assessment.time_limit or result.assessment.deadline:
        elapsed_time = int((current_time - result.start_time).total_seconds())
        time_limit = result.assessment.time_limit
        deadline = result.assessment.deadline

        remaining_time_until_deadline = int((deadline - current_time).total_seconds()) if deadline else float('inf')
        remaining_time_based_on_limit = int(time_limit - elapsed_time)
        remaining_time = int(min(remaining_time_based_on_limit, remaining_time_until_deadline))

        if remaining_time <= 0:
            return Response({'error': 'Time limit exceeded.'}, status=status.HTTP_404_NOT_FOUND)

        response_data['time_left'] = remaining_time

    result.last_activity = current_time
    result.score = score
    result.save()

    return Response(response_data, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@auth_required("student")
def take_exam(request):
    no_of_items = 60
    user: User = request.user
    selected_questions = list(Question.objects.order_by('?')[no_of_items:])

    exam = Assessment.objects.create(
        name=f"Practice Exam ({now().strftime('%Y-%m-%d %H:%M')})",
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

    thirty_minutes_ago = now() - timedelta(minutes=30)
    recent_quiz = Assessment.objects.filter(created_by=user, created_at__gte=thirty_minutes_ago).exists()

    if recent_quiz:
        return Response({'error': 'Student have already taken a quiz within 30 minutes. Please try again later!'},
                        status=status.HTTP_429_TOO_MANY_REQUESTS)

    if question_source == 'previous_exam':
        all_questions = Question.objects.filter(category_id__in=selected_categories)
        selected_questions = random.sample(list(all_questions), no_of_questions)

    elif question_source == 'ai_generated':
        return Response({'message': 'AI-generated questions feature has not been implemented yet.'},
                        status=status.HTTP_501_NOT_IMPLEMENTED)
    else:
        return Response({'message': 'AI-generated questions feature has not been implemented yet.'},
                        status=status.HTTP_501_NOT_IMPLEMENTED)

    categories = Category.objects.filter(id__in=selected_categories)

    quiz = Assessment.objects.create(
        name=f"Practice Quiz ({now().strftime('%Y-%m-%d %H:%M')})",
        created_by=user,
        type='quiz',
        question_source=question_source,
        source='student_initiated'
    )

    quiz.questions.set(selected_questions)
    quiz.selected_categories.set(categories)
    quiz.save()

    AssessmentResult.objects.create(assessment=quiz, user=user, start_time=now())

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
def lesson_assessment_limit(request, lesson_id):
    user: User = request.user
    lesson = get_object_or_404(Lesson, id=lesson_id)

    attempts_count = AssessmentResult.objects.filter(
        user=user,
        assessment__lesson=lesson,
        assessment__class_owner=user.enrolled_class
    ).count()

    max_attempts = 3
    remaining_attempts = max(max_attempts - attempts_count, 0)

    return Response({
        "remaining_attempts": remaining_attempts,
        "max_attempts": max_attempts
    })


@api_view(['GET'])
@auth_required("student")
def take_lesson_assessment(request, lesson_id):
    user: User = request.user
    lesson = get_object_or_404(Lesson, id=lesson_id)
    lesson_category = get_object_or_404(Category, name=lesson.name)

    attempts_count = AssessmentResult.objects.filter(
        user=user,
        assessment__lesson=lesson,
        assessment__class_owner=user.enrolled_class
    ).count()

    max_attempts = 3
    if attempts_count >= max_attempts:
        return Response(
            {"error": "Maximum of 3 quiz attempts reached."},
            status=status.HTTP_403_FORBIDDEN
        )

    no_of_questions = 1
    all_questions = list(Question.objects.filter(category_id=lesson_category.id))
    selected_questions = random.sample(list(all_questions), no_of_questions)

    lesson_assessment = Assessment.objects.create(
        name=f'Lesson Quiz: {lesson.name} Attempt {attempts_count + 1}',
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
                'choices': list(question.choices.values())
            }
            for question in selected_questions
        ]
    }

    AssessmentResult.objects.create(assessment=lesson_assessment, user=user, start_time=now())

    return Response(quiz_data, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@auth_required("student")
def chapter_assessment_limit(request, chapter_id):
    user: User = request.user
    chapter = get_object_or_404(Chapter, id=chapter_id)

    attempts_count = AssessmentResult.objects.filter(
        user=user,
        assessment__chapter=chapter,
        assessment__class_owner=user.enrolled_class
    ).count()

    max_attempts = 3
    remaining_attempts = max(max_attempts - attempts_count, 0)

    return Response({
        "remaining_attempts": remaining_attempts,
        "max_attempts": max_attempts
    })


@api_view(['GET'])
@auth_required("student")
def take_chapter_assessment(request, chapter_id):
    user: User = request.user
    chapter = get_object_or_404(Chapter, id=chapter_id)

    # Check if the student has exceeded attempts
    attempts_count = AssessmentResult.objects.filter(
        user=user,
        assessment__chapter=chapter,
        assessment__class_owner=user.enrolled_class
    ).count()

    max_attempts = 3
    if attempts_count >= max_attempts:
        return Response(
            {"error": "Maximum of 3 quiz attempts reached."},
            status=status.HTTP_403_FORBIDDEN
        )

    no_of_questions = 20
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
                'choices': list(question.choices.values())
            }
            for question in selected_questions
        ]
    }

    AssessmentResult.objects.create(assessment=chapter_assessment, user=user, start_time=now())

    return Response(quiz_data, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@auth_required("student")
def take_teacher_assessment(request, assessment_id):
    user: User = request.user

    assessment = get_object_or_404(Assessment.objects.prefetch_related("questions"), id=assessment_id,
                                   is_active=True)

    attempts_count = AssessmentResult.objects.filter(
        user=user,
        assessment=assessment
    ).count()

    max_attempts = 3
    if attempts_count >= max_attempts:
        return Response(
            {"error": "Maximum of 3 quiz attempts reached."},
            status=status.HTTP_403_FORBIDDEN
        )

    if user.enrolled_class != assessment.class_owner:
        return Response({'error': "Student doesn't belong to the class."}, status=status.HTTP_403_FORBIDDEN)

    quiz_data = {
        'quiz_id': assessment.id,
        'deadline': assessment.deadline,
        'type': assessment.type,
        'questions': [
            {
                'question_id': question.id,
                'image_url': question.image_url,
                'question_text': question.question_text,
                'choices': list(question.choices.values())
            }
            for question in assessment.questions.all()
        ],
        'attempts': attempts_count
    }

    return Response(quiz_data, status=status.HTTP_200_OK)


@api_view(['GET'])
@auth_required("student")
def teacher_assessment_limit(request, assessment_id):
    user: User = request.user

    assessment = get_object_or_404(Assessment.objects.prefetch_related("questions"), id=assessment_id,
                                   is_active=True)

    attempts_count = AssessmentResult.objects.filter(
        user=user,
        assessment=assessment,
    ).count()

    max_attempts = 3
    remaining_attempts = max(max_attempts - attempts_count, 0)

    return Response({
        "remaining_attempts": remaining_attempts,
        "max_attempts": max_attempts
    })


@api_view(['POST'])
@auth_required("student")
def submit_assessment(request, assessment_id):
    user: User = request.user
    current_time = timezone.now()

    assessment = get_object_or_404(Assessment, id=assessment_id, is_active=True)

    if assessment.source == 'student_initiated' and assessment.created_by != user:
        return Response({'error': 'You are not allowed to submit answers on this assessment'},
                        status=status.HTTP_403_FORBIDDEN)
    else:
        if assessment.class_owner and user.enrolled_class and assessment.class_owner != user.enrolled_class:
            return Response({'error': 'You are not allowed to submit answers on this assessment'},
                            status=status.HTTP_403_FORBIDDEN)

    result, created = AssessmentResult.objects.get_or_create(
        user=user,
        assessment_id=assessment_id,
        defaults={
            "is_submitted": False,
            "start_time": current_time,
        }
    )

    if result.is_submitted:
        return Response({'error': 'Assessment was already submitted.'}, status=status.HTTP_400_BAD_REQUEST)

    is_auto_submission = False

    if assessment.time_limit or assessment.deadline:
        end_time = result.start_time + timedelta(seconds=assessment.time_limit) if assessment.time_limit else None
        deadline_time = assessment.deadline if assessment.deadline else None

        if end_time and deadline_time:
            final_end_time = min(end_time, deadline_time)
        elif end_time:
            final_end_time = end_time
        else:
            final_end_time = deadline_time

        if current_time >= final_end_time - timedelta(seconds=AUTO_SUBMISSION_GRACE_PERIOD):
            is_auto_submission = True

        if not is_auto_submission and current_time >= final_end_time:
            return Response({'error': 'Submission not allowed. Time limit or deadline exceeded.'},
                            status=status.HTTP_400_BAD_REQUEST)

    answers = request.data.get('answers', [])

    if not answers:
        return Response({'error': 'No answers provided.'}, status=status.HTTP_400_BAD_REQUEST)

    result.time_take = (current_time - result.start_time).seconds

    assessment_questions = {q.id: q for q in assessment.questions.all()}
    answer_dict = {a["question_id"]: a for a in answers}

    existing_answers = {a.question_id: a for a in Answer.objects.filter(assessment_result=result)}

    score = 0
    answers_to_update = []
    answers_to_create = []

    for question_id, question in assessment_questions.items():
        answer_data = answer_dict.get(question_id)
        if not answer_data:
            continue  # Skip if no answer is provided

        chosen_answer = answer_data.get('answer')
        time_spent = answer_data.get('time_spent', 0)
        correct_answer = question.choices[question.correct_answer]
        is_correct = chosen_answer == correct_answer
        score += int(is_correct)

        if question_id in existing_answers:
            # Update the existing answer
            existing_answer = existing_answers[question_id]
            existing_answer.chosen_answer = chosen_answer
            existing_answer.is_correct = is_correct
            existing_answer.time_spent = time_spent
            answers_to_update.append(existing_answer)
        else:
            # Create a new answer
            answers_to_create.append(Answer(
                assessment_result=result,
                question=question,
                time_spent=time_spent,
                chosen_answer=chosen_answer,
                is_correct=is_correct
            ))

    # Bulk update existing answers
    if answers_to_update:
        Answer.objects.bulk_update(answers_to_update, ['chosen_answer', 'is_correct', 'time_spent'])

    # Bulk create new answers
    if answers_to_create:
        Answer.objects.bulk_create(answers_to_create)

    result.time_taken = (current_time - result.start_time).seconds
    result.score = score
    result.is_submitted = True
    result.save()

    return Response({'message': 'Assessment was submitted successfully'}, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@auth_required("student")
def submit_class_assessment(request, assessment_id):
    user: User = request.user
    assessment = get_object_or_404(Assessment, id=assessment_id, is_active=True)

    if assessment.source == 'student_initiated' and assessment.created_by != user:
        return Response({'error': 'You are not allowed to submit answers on this assessment'},
                        status=status.HTTP_403_FORBIDDEN)
    else:
        if assessment.class_owner and user.enrolled_class and assessment.class_owner != user.enrolled_class:
            return Response({'error': 'You are not allowed to submit answers on this assessment'},
                            status=status.HTTP_403_FORBIDDEN)

    previous_results = AssessmentResult.objects.filter(
        user=user,
        assessment_id=assessment_id,
    )

    if previous_results.count() == 3:
        return Response({
            'error': 'Maximum attempts has been reached.',
        }, status=status.HTTP_400_BAD_REQUEST)

    result = AssessmentResult.objects.create(
        user=user,
        assessment_id=assessment_id,
        start_time=timezone.now(),
    )

    is_auto_submission = False

    current_time = timezone.now()
    if assessment.deadline:
        deadline_time = assessment.deadline if assessment.deadline else None

        if current_time >= deadline_time - timedelta(seconds=AUTO_SUBMISSION_GRACE_PERIOD):
            is_auto_submission = True

        if not is_auto_submission and current_time >= deadline_time:
            return Response({'error': 'Submission not allowed. Time limit or deadline exceeded.'},
                            status=status.HTTP_400_BAD_REQUEST)

    answers = request.data.get('answers', [])

    if not answers:
        return Response({'error': 'No answers provided.'}, status=status.HTTP_400_BAD_REQUEST)

    result.time_take = (current_time - result.start_time).seconds

    assessment_questions = {q.id: q for q in assessment.questions.all()}
    answer_dict = {a["question_id"]: a for a in answers}

    existing_answers = {a.question_id: a for a in Answer.objects.filter(assessment_result=result)}

    score = 0
    answers_to_update = []
    answers_to_create = []

    for question_id, question in assessment_questions.items():
        answer_data = answer_dict.get(question_id)
        if not answer_data:
            continue  # Skip if no answer is provided

        chosen_answer = answer_data.get('answer')
        time_spent = answer_data.get('time_spent', 0)
        correct_answer = question.choices[question.correct_answer]
        is_correct = chosen_answer == correct_answer
        score += int(is_correct)

        if question_id in existing_answers:
            # Update the existing answer
            existing_answer = existing_answers[question_id]
            existing_answer.chosen_answer = chosen_answer
            existing_answer.is_correct = is_correct
            existing_answer.time_spent = time_spent
            answers_to_update.append(existing_answer)
        else:
            # Create a new answer
            answers_to_create.append(Answer(
                assessment_result=result,
                question=question,
                time_spent=time_spent,
                chosen_answer=chosen_answer,
                is_correct=is_correct
            ))

    # Bulk update existing answers
    if answers_to_update:
        Answer.objects.bulk_update(answers_to_update, ['chosen_answer', 'is_correct', 'time_spent'])

    # Bulk create new answers
    if answers_to_create:
        Answer.objects.bulk_create(answers_to_create)

    result.time_taken = (current_time - result.start_time).seconds
    result.score = score
    result.is_submitted = True
    result.save()

    return Response({'message': 'Assessment was submitted successfully'}, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@auth_required("student")
def get_assessment_result(request, assessment_id):
    user = request.user
    result = AssessmentResult.objects.select_related('assessment', 'user').prefetch_related(
        Prefetch('answers', queryset=Answer.objects.select_related('question__category')),
        Prefetch('assessment__questions', queryset=Question.objects.select_related('category'))
    ).filter(
        assessment__id=assessment_id,
        user=request.user
    ).order_by('-id').first()

    if result is None:
        return Response({'error': 'No Result for Assessment Found'}, status=status.HTTP_404_NOT_FOUND)

    if not result.is_submitted and (result.assessment.time_limit or result.assessment.deadline):
        time_limit = result.start_time + timedelta(
            seconds=result.assessment.time_limit) if result.assessment.time_limit else None

        expected_end = min(time_limit, result.assessment.deadline)

        if expected_end > timezone.now():
            return Response({'error': 'Assessment is still in progress.'}, status=status.HTTP_400_BAD_REQUEST)

    answers = result.answers.all()
    answer_dict = {ans.question.id: ans for ans in answers}

    questions = result.assessment.questions.all()

    overall_correct_answers = 0
    overall_wrong_answers = 0
    category_stats = defaultdict(lambda: {'total_questions': 0, 'correct_answers': 0, 'wrong_answers': 0})

    serialized_answers = []
    for question in questions:

        category_name = question.category.name
        category_stats[category_name]['total_questions'] += 1

        answer = answer_dict.get(question.id)

        if answer:
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
        else:
            category_stats[category_name]['wrong_answers'] += 1
            overall_wrong_answers += 1

            serialized_answers.append({
                'question_id': question.id,
                'question_text': question.question_text,
                'choices': question.choices if isinstance(question.choices, list) else list(question.choices.values()),
                'chosen_answer': None,
                'is_correct': False,
                'time_spent': None,
            })

    categories = [
        {
            'category_name': category_name,
            **stats
        }
        for category_name, stats in category_stats.items()
    ]

    if result.time_taken:
        time_taken = result.time_taken
    else:
        time_taken = int((result.last_activity - result.start_time).total_seconds())
        result.time_taken = time_taken
        result.save()
        result.is_submitted = True

    result_data = {
        'exam_id': result.assessment.id,
        'student_id': result.user.id,
        'score': result.score,
        'total_time_taken_seconds': time_taken,
        'total_questions': questions.count(),
        'overall_correct_answers': overall_correct_answers,
        'overall_wrong_answers': overall_wrong_answers,
        'categories': categories,
        'answers': serialized_answers,
    }

    return Response(result_data, status=status.HTTP_200_OK)

@api_view(['GET'])
@auth_required("student")
def get_class_assessment_result(request, assessment_id):
    user: User = request.user

    # Get the assessment and verify student access
    assessment = get_object_or_404(
        Assessment.objects.select_related('class_owner'),
        id=assessment_id,
        is_active=True
    )

    # Verify student belongs to the class
    if user.enrolled_class != assessment.class_owner:
        return Response({'error': 'You are not enrolled in this class'},
                        status=status.HTTP_403_FORBIDDEN)

    # Get all attempts for this student (max 3)
    attempts = AssessmentResult.objects.filter(
        assessment=assessment,
        user=user
    ).order_by('-start_time')[:3]  # Get most recent 3 attempts

    if not attempts.exists():
        return Response({'error': 'No attempts found for this assessment'},
                        status=status.HTTP_404_NOT_FOUND)

    # Prefetch related data for all attempts
    attempts = attempts.prefetch_related(
        Prefetch('answers', queryset=Answer.objects.select_related('question__category')),
        Prefetch('assessment__questions', queryset=Question.objects.select_related('category'))
    )

    attempt_data = []
    for attempt in attempts:
        # Process each attempt similar to original logic
        answers = attempt.answers.all()
        answer_dict = {ans.question.id: ans for ans in answers}
        questions = attempt.assessment.questions.all()

        # Calculate statistics for this attempt
        overall_correct = 0
        overall_wrong = 0
        category_stats = defaultdict(lambda: {'total_questions': 0, 'correct': 0, 'wrong': 0})

        serialized_answers = []
        for question in questions:
            category_name = question.category.name
            category_stats[category_name]['total_questions'] += 1

            answer = answer_dict.get(question.id)

            if answer:
                if answer.is_correct:
                    category_stats[category_name]['correct'] += 1
                    overall_correct += 1
                else:
                    category_stats[category_name]['wrong'] += 1
                    overall_wrong += 1

                serialized_answers.append({
                    'question_id': answer.question.id,
                    'question_text': answer.question.question_text,
                    'choices': answer.question.choices,
                    'chosen_answer': answer.chosen_answer,
                    'is_correct': answer.is_correct,
                    'time_spent': answer.time_spent,
                })
            else:
                category_stats[category_name]['wrong'] += 1
                overall_wrong += 1

                serialized_answers.append({
                    'question_id': question.id,
                    'question_text': question.question_text,
                    'is_correct': False,
                    'time_spent': None,
                })

        # Calculate time taken for this attempt
        if attempt.time_taken:
            time_taken = attempt.time_taken
        else:
            time_taken = int((attempt.last_activity - attempt.start_time).total_seconds())

        attempt_data.append({
            'attempt_number': attempts.count() - list(attempts).index(attempt),  # 1-based numbering
            'start_time': attempt.start_time,
            'time_taken_seconds': time_taken,
            'score': attempt.score,
            'total_questions': questions.count(),
            'correct_answers': overall_correct,
            'wrong_answers': overall_wrong,
            'categories': [
                {
                    'category_name': name,
                    'correct_answers': stats['correct'],
                    'total_questions': stats['total_questions'],
                    'accuracy_percent': round((stats['correct'] / stats['total_questions']) * 100, 2)
                    if stats['total_questions'] > 0 else 0
                }
                for name, stats in category_stats.items()
            ],
            'answers': serialized_answers
        })

    # Sort attempts from latest to oldest
    attempt_data.reverse()

    response_data = {
        'assessment_id': assessment.id,
        'assessment_name': assessment.name,
        'max_attempts': 3,
        'attempts_remaining': 3 - attempts.count(),
        'total_attempts': attempts.count(),
        'attempts': attempt_data
    }

    return Response(response_data, status=status.HTTP_200_OK)


@api_view(['GET'])
@auth_required("student")
def get_ability(request):
    user: User = request.user

    estimate_ability_irt(user.id)
    estimate_ability_elo(user.id)

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

    print('user', user)

    assessments = Assessment.objects.filter(source='teacher_generated', class_owner=user.enrolled_class,
                                            is_active=True).order_by('-created_at')
    assessments_data = []

    for assessment in assessments:
        results = AssessmentResult.objects.filter(assessment=assessment, user=user)
        is_open = assessment.deadline is None or assessment.deadline >= timezone.now()

        if not results:
            assessment_status = 'Not Started'
        elif results.count() == 3:
            assessment_status = 'Completed'
        else:
            assessment_status = 'Open'

        data = {
            'id': assessment.id,
            'name': assessment.name,
            'type': assessment.type,
            'items': assessment.questions.count(),
            'is_open': is_open,
            'status': assessment_status,
            'attempts_left': 3 - results.count()
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
                'wrong_answer': wrong_answers,
                'percentage': (correct_answers / (correct_answers + wrong_answers) * 100) if (
                                                                                                     correct_answers + wrong_answers) > 0 else 0
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

    return Response(chapter_data, status=status.HTTP_200_OK)


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
