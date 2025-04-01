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

    # Generate lesson data efficiently using list comprehension
    lesson_data = [
        {
            "id": lesson.id,
            "lesson_name": lesson.name,
            "is_locked": lesson.is_locked,
        }
        for lesson in lessons
    ]

    assessment_results = AssessmentResult.objects.filter(user__id=user.id).order_by('-start_time')

    history_data = []
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

    if user.enrolled_class:
        exists = AssessmentResult.objects.filter(
            assessment__class_owner=user.enrolled_class,
            assessment__is_initial=True,
            user=user
        ).exists()

        return Response({'taken': exists}, status=status.HTTP_200_OK)
    else:
        return Response({"error": "Student is not enrolled to a class"}, status=status.HTTP_403_FORBIDDEN)


@api_view(['GET'])
@auth_required("student")
def take_initial_exam(request):
    user: User = request.user
    current_time = timezone.now()

    exam = Assessment.objects.filter(
        class_owner=user.enrolled_class, is_initial=True, is_active=True
    ).select_related("class_owner").prefetch_related("questions").only("id", "time_limit", "deadline",
                                                                       "class_owner").first()

    if user.enrolled_class is None:
        return Response({'error': "Student is not enrolled in any class"}, status=status.HTTP_403_FORBIDDEN)

    if not exam:
        return Response({"error": "Initial Exam doesn't exist"}, status=status.HTTP_404_NOT_FOUND)

    if not exam.deadline:
        return Response({'error': 'Initial Exam is not open'}, status=status.HTTP_400_BAD_REQUEST)

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

    questions = list(exam.questions.values("id", "image_url", "question_text", "choices"))
    # random.shuffle(questions)

    answers = Answer.objects.filter(assessment_result=result)

    # Convert answers into a dictionary for quick lookup
    answers_dict = {
        answer.question_id: {
            'chosen_answer': answer.chosen_answer,  # The user's selected choice
            'time_spent': answer.time_spent  # Optional: Include time taken
        }
        for answer in answers
    }

    questions_data = []
    for question in questions:
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
        'no_of_items': len(questions),
        'time_limit': int(remaining_time),
        'questions': questions_data,
        'question_ids': [q["id"] for q in questions],
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

    try:
        result = AssessmentResult.objects.get(user=user, assessment__id=assessment_id)
    except AssessmentResult.DoesNotExist:
        return Response({'error': 'Assessment result not found.'}, status=status.HTTP_404_NOT_FOUND)

    # Fetch all the questions upfront to avoid N+1 queries
    question_ids = [answer_data.get('question_id') for answer_data in answers]
    questions = {question.id: question for question in Question.objects.filter(id__in=question_ids)}

    # Prepare bulk update for existing answers and bulk create for new ones
    answers_to_update = []
    answers_to_create = []

    # Get existing answers
    existing_answers = Answer.objects.filter(assessment_result=result, question__id__in=question_ids)
    existing_answers_dict = {(answer.question.id): answer for answer in existing_answers}

    for answer_data in answers:
        question_id = answer_data.get('question_id')
        chosen_answer = answer_data.get('answer')
        time_spent = int(answer_data.get('time_spent', 0))

        question = questions.get(question_id)
        if question:
            existing_answer = existing_answers_dict.get(question_id)
            correct_answer = question.choices[question.correct_answer]
            is_correct = chosen_answer == correct_answer

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

    # Calculate remaining time
    elapsed_time = int((current_time - result.start_time).total_seconds())
    time_limit = result.assessment.time_limit
    deadline = result.assessment.deadline

    remaining_time_until_deadline = int((deadline - current_time).total_seconds()) if deadline else float('inf')
    remaining_time_based_on_limit = int(time_limit - elapsed_time)
    remaining_time = int(min(remaining_time_based_on_limit, remaining_time_until_deadline))

    if remaining_time <= 0:
        return Response({'error': 'Time limit exceeded.'}, status=status.HTTP_404_NOT_FOUND)

    result.last_activity = current_time
    result.save()

    return Response({'message': 'Progress was stored successfully', 'time_left': remaining_time},
                    status=status.HTTP_201_CREATED)


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
    lesson = get_object_or_404(Lesson, id=lesson_id)
    lesson_category = get_object_or_404(Category, name=lesson.name)

    thirty_minutes_ago = now() - timedelta(minutes=30)
    recent_quiz = Assessment.objects.filter(lesson=lesson, class_owner=user.enrolled_class,
                                            created_at__gte=thirty_minutes_ago).exists()

    if recent_quiz:
        return Response({'error': 'Student have already taken a quiz within 30 minutes. Please try again later!'},
                        status=status.HTTP_429_TOO_MANY_REQUESTS)

    no_of_questions = 20
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
    chapter = get_object_or_404(Chapter, id=chapter_id)
    thirty_minutes_ago = now() - timedelta(minutes=30)
    recent_quiz = Assessment.objects.filter(chapter=chapter, class_owner=user.enrolled_class,
                                            created_at__gte=thirty_minutes_ago).exists()

    if recent_quiz:
        return Response({'error': 'Student have already taken a quiz within 30 minutes. Please try again later!'},
                        status=status.HTTP_429_TOO_MANY_REQUESTS)

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

    assessment = get_object_or_404(Assessment.objects.prefetch_related("questions"), assessment__id=assessment_id,
                                   is_active=True)

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
                'choices': question.choices
            }
            for question in assessment.questions
        ]
    }

    return Response(quiz_data, status=status.HTTP_200_OK)


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

    result = AssessmentResult.objects.filter(user=user, assessment_id=assessment_id).first()

    if not result:
        return Response({'error': 'Assessment result not found.'}, status=status.HTTP_404_NOT_FOUND)

    if result.is_submitted:
        return Response({'error': 'Exam was already submitted.'}, status=status.HTTP_400_BAD_REQUEST)

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

    result.time_taken = (current_time - result.start_time).second()
    result.score = score
    result.is_submitted = True
    result.save()

    return Response({'message': 'Assessment was submitted successfully'}, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@auth_required("student")
def get_assessment_result(request, assessment_id):
    user: User = request.user
    result = AssessmentResult.objects.select_related('assessment', 'user').prefetch_related(
        Prefetch('answers', queryset=Answer.objects.select_related('question__category')),
        Prefetch('assessment__questions', queryset=Question.objects.select_related('category'))
    ).filter(assessment__id=assessment_id, user=user).first()

    if result is None:
        return Response({'error': 'No Result for Assessment Found'}, status=status.HTTP_404_NOT_FOUND)

    time_limit = result.start_time + timedelta(
        seconds=result.assessment.time_limit) if result.assessment.time_limit else None

    print('Time limit', time_limit)
    print('Deadline', result.assessment.deadline)

    expected_end = min(time_limit, result.assessment.deadline)

    print('Expected end time', expected_end)
    print('Time now', timezone.now())

    if not result.is_submitted and expected_end > timezone.now():
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
        'total_time_taken_seconds': time_taken,
        'score': result.score,
        'categories': categories,
        'overall_correct_answers': overall_correct_answers,
        'overall_wrong_answers': overall_wrong_answers,
        'total_questions': questions.count(),
        'answers': serialized_answers,
    }

    return Response(result_data, status=status.HTTP_200_OK)


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

    assessments = Assessment.objects.filter(source='teacher_generated', class_owner=user.enrolled_class,
                                            is_active=True).order_by(
        '-created_at')
    assessments_data = []

    for assessment in assessments:
        result = AssessmentResult.objects.filter(assessment=assessment, user=user).first()
        is_open = assessment.deadline is None or assessment.deadline >= timezone.now()

        if not result:
            assessment_status = 'Open'
        elif result.is_submitted:
            assessment_status = 'Completed'
        else:
            expected_end_time = result.start_time + result.assessment.time_limit
            end_time = min(expected_end_time, result.assessment.deadline)
            assessment_status = 'In Progress' if end_time >= timezone.now() else 'Completed'

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
