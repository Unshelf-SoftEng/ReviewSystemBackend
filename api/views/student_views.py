from http import HTTPStatus

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
import random
from ..models import User, Question, Assessment, Answer, AssessmentResult, UserAbility, Category, Class, Lesson, \
    LessonProgress, Class
from collections import defaultdict
from ..ai.estimate_student_ability import estimate_student_ability_per_category
from api.views.general_views import get_user_id_from_token
from django.shortcuts import get_object_or_404


@api_view(['GET'])
def get_class(request):
    supabase_uid = get_user_id_from_token(request)

    if not supabase_uid:
        return Response({'error': 'User not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)

    try:
        user = User.objects.get(supabase_user_id=supabase_uid)
    except User.DoesNotExist:
        return Response({'error': 'User does not exist.'}, status=status.HTTP_404_NOT_FOUND)

    if user.role != 'student':
        return Response({"error": "You are not authorized to access this link"}, status=status.HTTP_403_FORBIDDEN)

    # Get the classes the student is enrolled in
    if user.enrolled_class is None:
        return Response({"message": "You are not enrolled in any class."}, status=status.HTTP_200_OK)

    lessons = Lesson.objects.all()
    lesson_data = []
    for lesson in lessons:

        progress = LessonProgress.objects.filter(user=user, lesson=lesson).first()

        if not progress:
            progress = LessonProgress(user=user, lesson=lesson)

        progress_percentage = progress.progress_percentage if progress else 0.0  # Default to 0% if no progress

        lesson_data.append({
            "id": lesson.id,
            "lesson_name": lesson.lesson_name,
            "progress_percentage": progress_percentage
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
def join_class(request):
    supabase_uid = get_user_id_from_token(request)

    if not supabase_uid:
        return Response({'error': 'User not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)

    try:
        user = User.objects.get(supabase_user_id=supabase_uid)
    except User.DoesNotExist:
        return Response({'error': 'User does not exist.'}, status=status.HTTP_404_NOT_FOUND)

    if user.role != 'student':
        return Response({"error": "You are not authorized to access this link"}, status=status.HTTP_403_FORBIDDEN)

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
def get_initial_exam(request):
    supabase_uid = get_user_id_from_token(request)

    if not supabase_uid:
        return Response({'error': 'User not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)

    try:
        user = User.objects.get(supabase_user_id=supabase_uid)
    except User.DoesNotExist:
        return Response({'error': 'User does not not exist.'}, status=status.HTTP_404_NOT_FOUND)

    if user.role != 'student':
        return Response({"error": "You are not authorized to access this link."}, status=status.HTTP_403_FORBIDDEN)

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


def initial_exam_taken(request):
    supabase_uid = get_user_id_from_token(request)

    if not supabase_uid:
        return Response({'error': 'User not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)

    try:
        user = User.objects.get(supabase_user_id=supabase_uid)
    except User.DoesNotExist:
        return Response({'error': 'User does not not exist.'}, status=status.HTTP_404_NOT_FOUND)

    if user.role != 'student':
        return Response({"error": "You are not authorized to access this link."}, status=status.HTTP_403_FORBIDDEN)

    if user.enrolled_class is None:
        return Response({"error": "Student is not enrolled to a class"}, status=status.HTTP_403_FORBIDDEN)

    # Retrieve the exam object; ensure that the exam belongs to the authenticated user
    exam = get_object_or_404(Assessment, class_owner=user.enrolled_class, is_initial=True)

    exam_result = AssessmentResult.objects.filter(exam=exam, user=user)

    return Response({"taken": exam_result.exists()}, status=status.HTTP_200_OK)


@api_view(['GET'])
def take_initial_exam(request):
    supabase_uid = get_user_id_from_token(request)

    if not supabase_uid:
        return Response({'error': 'User not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)

    try:
        user = User.objects.get(supabase_user_id=supabase_uid)
    except User.DoesNotExist:
        return Response({'error': 'User does not exist.'}, status=status.HTTP_404_NOT_FOUND)

    if user.role != 'student':
        return Response({"error": "You are not authorized to access this link"}, status=403)

    exam = Assessment.objects.filter(class_owner=user.enrolled_class, is_initial=True).first()

    if exam is None:
        return Response({"error": "Can't find initial exam"}, status=status.HTTP_404_NOT_FOUND)

    if exam.deadline is None:
        return Response({'error': 'Exam deadline is not open.'}, status=status.HTTP_400_BAD_REQUEST)

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

    return Response(exam_data, status=status.HTTP_200_OK)


@api_view(['GET'])
def take_exam(request):
    supabase_uid = get_user_id_from_token(request)

    if not supabase_uid:
        return Response({'error': 'User not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)

    try:
        user = User.objects.get(supabase_user_id=supabase_uid)
    except User.DoesNotExist:
        return Response({'error': 'User does not exist.'}, status=status.HTTP_404_NOT_FOUND)

    if user.role != 'student':
        return Response({"error": "You are not authorized to access this link"}, status=403)

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
        status="created"
    )

    categories = set()
    for question in selected_questions:
        category = Category.objects.get(id=question.category_id)
        categories.add(category)

    exam.selected_categories.set(categories)
    exam.questions.set(selected_questions)
    exam.time_limit = 90 * len(selected_questions)
    exam.status = "in_progress"
    exam.save()

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


@api_view(['POST'])
def submit_assessment(request, assessment_id):
    supabase_uid = get_user_id_from_token(request)

    if not supabase_uid:
        return Response({'error': 'User not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)

    try:
        user = User.objects.get(supabase_user_id=supabase_uid)
    except User.DoesNotExist:
        return Response({'error': 'User does not exist.'}, status=status.HTTP_404_NOT_FOUND)

    if user.role != 'student':
        return Response({"error": "You are not authorized to access this link."}, status=status.HTTP_403_FORBIDDEN)

    # Retrieve the exam object
    exam = get_object_or_404(Assessment, id=assessment_id)

    data = request.data
    answers = data.get('answers', [])

    if not answers:
        return Response({'error': 'No answers provided.'}, status=status.HTTP_400_BAD_REQUEST)

    # Get the question IDs from the assessment
    assessment = Assessment.objects.get(id=exam.id)
    assessment_question_ids = set(assessment.questions.values_list('id', flat=True))

    # Get the question IDs from the answers
    answer_question_ids = set(answer_data.get('question_id') for answer_data in answers)

    # Check if the provided question IDs match the assessment questions
    if answer_question_ids != assessment_question_ids:
        return Response({
            'error': 'Submitted answers do not match the assessment questions.',
            'missing_questions': list(assessment_question_ids - answer_question_ids),
            'extra_questions': list(answer_question_ids - assessment_question_ids),
        }, status=status.HTTP_400_BAD_REQUEST)

    # Check if exam was already taken
    if AssessmentResult.objects.filter(assessment=assessment, user=user).exists():
        return Response({'error': 'Exam was already taken.'}, status=status.HTTP_400_BAD_REQUEST)

    # Create exam result entry
    assessment_result = AssessmentResult.objects.create(
        assessment=exam,
        score=0,
        time_taken=0,
        user=user
    )

    score = 0
    for answer_data in answers:
        question_id = answer_data.get('question_id')
        chosen_answer = answer_data.get('answer')
        time_spent = answer_data.get('time_spent', 0)

        question = get_object_or_404(Question, id=question_id)
        correct_answer = question.choices[question.correct_answer]

        is_correct = chosen_answer == correct_answer
        if is_correct:
            score += 1

        Answer.objects.create(
            assessment_result=assessment_result,
            question=question,
            time_spent=time_spent,
            chosen_answer=chosen_answer,
            is_correct=is_correct
        )

    assessment_result.score = score
    assessment_result.time_taken = data.get('total_time_taken_seconds', 0)
    assessment_result.save()

    return Response({'message': 'Exam submitted successfully.'}, status=status.HTTP_201_CREATED)


@api_view(['GET'])
def get_exam_results(request, assessment_id):
    supabase_uid = get_user_id_from_token(request)

    if not supabase_uid:
        return Response({'error': 'User not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)

    try:
        user = User.objects.get(supabase_user_id=supabase_uid)
    except User.DoesNotExist:
        return Response({'error': 'User does not exist.'}, status=status.HTTP_404_NOT_FOUND)

    if user.role != 'student':
        return Response({"error": "You are not authorized to access this link."}, status=403)

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
        'total_questions': len(answers),
        'answers': serialized_answers,  # Include answers in response
    }

    return Response(result_data, status=status.HTTP_200_OK)


@api_view(['GET'])
def get_ability(request):
    supabase_uid = get_user_id_from_token(request)

    if not supabase_uid:
        return Response({'error': 'User not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)

    try:
        user = User.objects.get(supabase_user_id=supabase_uid)
    except User.DoesNotExist:
        return Response({'error': 'User does not exist.'}, status=status.HTTP_404_NOT_FOUND)

    if user.role != 'student':
        return Response({"error": "You are not authorized to access this link."}, status=403)

    estimate_student_ability_per_category(user.id)

    # Retrieve stored abilities
    user_abilities = UserAbility.objects.filter(user_id=user.id)
    stored_abilities = {
        user_ability.category.name: user_ability.ability_level for user_ability in user_abilities
    }

    return Response({
        "abilities": stored_abilities,
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
def take_quiz(request):
    supabase_uid = get_user_id_from_token(request)

    if not supabase_uid:
        return Response({'error': 'User not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)

    try:
        user = User.objects.get(supabase_user_id=supabase_uid)
    except User.DoesNotExist:
        return Response({'error': 'User does not exist.'}, status=status.HTTP_404_NOT_FOUND)

    if user.role != 'student':
        return Response({"error": "You are not authorized to access this link"}, status=403)

    selected_categories = request.GET.getlist('selected_categories')
    selected_categories = list(map(int, selected_categories)) if selected_categories else []

    no_of_questions = int(request.GET.get('no_of_questions', 5))
    question_source = request.GET.get('question_source')

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



@api_view(['GET'])
def take_lesson_quiz(request):
    supabase_uid = get_user_id_from_token(request)

    if not supabase_uid:
        return Response({'error': 'User not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)

    try:
        user = User.objects.get(supabase_user_id=supabase_uid)
    except User.DoesNotExist:
        return Response({'error': 'User does not exist.'}, status=status.HTTP_404_NOT_FOUND)

    if user.role != 'student':
        return Response({"error": "You are not authorized to access this link"}, status=403)

    data = request.data

    lesson_name = data.get('lesson')

    lesson = Lesson.objects.get(lesson_name=lesson_name)
    category = Category.objects.get(name=lesson_name)
    selected_categories = [category.id]
    question_source = data.get('question_source')
    no_of_questions = data.get('no_of_questions')

    if question_source == 'previous_exam':
        # Get all questions from the category
        all_questions = Question.objects.filter(category_id__in=selected_categories)

        if all_questions.count() < no_of_questions:
            return Response({'error': 'No questions available to generate an exam.'}, status=status.HTTP_404_NOT_FOUND)

        selected_questions = random.sample(list(all_questions), no_of_questions)

    elif question_source == 'ai_generated':
        return Response({'message': 'AI-generated questions feature has not been implemented yet.'},
                        status=status.HTTP_501_NOT_IMPLEMENTED)
    else:
        # pe_questions = random.choice(no_of_questions)
        #
        # all_questions = Question.objects.filter(category_id__in=selected_categories)
        #
        # if not all_questions:
        #     return Response({'error': 'No questions available to generate an exam'}, status=status.HTTP_404_NOT_FOUND)
        #
        # selected_questions = random.sample(list(all_questions), pe_questions)

        return Response({'message': 'AI-generated questions feature has not been implemented yet.'},
                        status=status.HTTP_501_NOT_IMPLEMENTED)

    lesson_quiz = Assessment.objects.create(
        lesson=lesson,
        created_by=user,
        type='Quiz',
        question_source='previous_exam',
        source='lesson',
    )

    lesson_quiz.selected_categories.set(selected_categories)
    lesson_quiz.questions.set(selected_questions)
    lesson_quiz.save()

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

    return Response(quiz_data, status=status.HTTP_200_OK)


@api_view(['GET'])
def get_class_assessments(request):
    supabase_uid = get_user_id_from_token(request)

    if not supabase_uid:
        return Response({'error': 'User not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)

    try:
        user = User.objects.get(supabase_user_id=supabase_uid)
    except User.DoesNotExist:
        return Response({'error': 'User does not exist.'}, status=status.HTTP_404_NOT_FOUND)

    if user.role != 'student':
        return Response({"error": "You are not authorized to access this link"}, status=403)

    class_owner = Class.objects.get(id=user.enrolled_class.id)
    assessments = Assessment.objects.filter(class_owner=class_owner, type='quiz')

    assessments_data = {
        'assessments': [
            {
                'assessment_id': assessment.id,
                'assessment_name': assessment.assessment_name,
                'assessment_type': assessment.type,
                'assessment_items': assessment.questions.count(),
            }
            for assessment in assessments
        ]
    }

    return Response(assessments_data, status=status.HTTP_200_OK)


@api_view(['GET'])
def get_history(request):
    supabase_uid = get_user_id_from_token(request)

    if not supabase_uid:
        return Response({'error': 'User not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)

    try:
        user = User.objects.get(supabase_user_id=supabase_uid)
    except User.DoesNotExist:
        return Response({'error': 'User does not exist.'}, status=status.HTTP_404_NOT_FOUND)

    if user.role != 'student':
        return Response({"error": "You are not authorized to access this link"}, status=403)

    assessments = Assessment.objects.filter(user_id=user.id).prefetch_related('selected_categories')

    history = []
    for assessment in assessments:
        result = AssessmentResult.objects.filter(assessment=assessment).first()

        # Skip if no result exists
        if not result:
            continue

        categories = list(assessment.selected_categories.values_list('name', flat=True))

        print(categories)

        item = {
            'assessment_id': assessment.id,
            'type': assessment.type,
            'score': result.score,
            'total_items': assessment.questions.count(),
            'time_taken': result.time_taken,
            'date_taken': assessment.created_at,
            'categories': categories,
            'question_source': assessment.question_source,
            'source': assessment.source
        }

        history.append(item)

    return Response(history, status=status.HTTP_200_OK)
