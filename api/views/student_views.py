from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
import random
from ..models import User, Question, Assessment, Answer, AssessmentResult, UserAbility, Category, Class
from collections import defaultdict
from ..ai.estimate_student_ability import estimate_student_ability_per_category
from api.views.general_views import get_user_id_from_token
from django.shortcuts import get_object_or_404


@api_view(['GET'])
def take_exam(request):
    supabase_uid = get_user_id_from_token(request)

    if not supabase_uid:
        return Response({'error': 'User not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)

    # Get all questions from the database
    all_questions = Question.objects.all()

    if not all_questions:
        return Response({'error': 'No questions available to generate an exam.'}, status=status.HTTP_404_NOT_FOUND)

    selected_questions = random.sample(list(all_questions), 5)

    user = User.objects.get(supabase_user_id=supabase_uid)

    # Create a new exam instance for the authenticated user
    exam = Assessment.objects.create(user=user, type='Exam')

    categories = set()  # Use a set to avoid duplicates
    for question in selected_questions:
        category = Category.objects.get(id=question.category_id)
        categories.add(category)

    exam.selected_categories.set(categories)
    exam.questions.set(selected_questions)
    exam.save()

    # Format the questions and answers to send back to the frontend
    exam_data = {
        'exam_id': exam.id,
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
def submit_exam(request, exam_id):
    supabase_uid = get_user_id_from_token(request)

    if not supabase_uid:
        return Response({'error': 'User not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)

    data = request.data

    # Retrieve the exam object; ensure that the exam belongs to the authenticated user
    exam = get_object_or_404(Assessment, id=exam_id)
    if exam.user.supabase_user_id != supabase_uid:
        return Response({'error': 'You are not authorized to submit answers for this exam.'},
                        status=status.HTTP_403_FORBIDDEN)

    # Parse answers from request
    answers = data.get('answers', [])

    # Initialize tracking variables
    score = 0

    check_if_exists = AssessmentResult.objects.filter(assessment_id=exam_id).exists()

    if check_if_exists:
        return Response({'error': 'Exam was already taken.'}, status=status.HTTP_400_BAD_REQUEST)

    # Create an AssessmentResult object
    exam_result = AssessmentResult.objects.create(
        assessment=exam,
        score=0,  # Placeholder; updated after processing
        time_taken=0  # Placeholder; updated after processing
    )

    for answer_data in answers:
        question_id = answer_data.get('question_id')
        chosen_answer = answer_data.get('answer')
        time_spent = answer_data.get('time_spent', 0)

        # Get the corresponding question
        question = get_object_or_404(Question, id=question_id)

        # Check if the chosen answer is correct
        correct_answer = question.choices[question.correct_answer]

        is_correct = chosen_answer == correct_answer

        if is_correct:
            score += 1

        # Save answer to the database
        Answer.objects.create(
            exam_result=exam_result,
            question=question,
            time_spent=time_spent,
            chosen_answer=chosen_answer,
            is_correct=is_correct
        )

    exam_result.score = score
    exam_result.time_taken = data.get('total_time_taken_seconds', 0)
    exam_result.save()

    user_id = User.objects.get(supabase_user_id=supabase_uid).id

    estimate_student_ability_per_category(user_id)

    return Response({'message': 'Exam submitted successfully.'}, status=status.HTTP_201_CREATED)


@api_view(['GET'])
def get_exam_results(request, exam_id):
    supabase_uid = get_user_id_from_token(request)

    if not supabase_uid:
        return Response({'error': 'User not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)

    # Retrieve the exam object; ensure that the exam belongs to the authenticated user
    exam = get_object_or_404(Assessment, id=exam_id)
    exam_results = get_object_or_404(AssessmentResult, assessment=exam)
    answers = Answer.objects.filter(exam_result=exam_results)

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
        'student_id': exam.user.id,
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
        user_id = User.objects.get(supabase_user_id=supabase_uid).id
    except User.DoesNotExist:
        return Response({'error': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)

    estimate_student_ability_per_category(user_id)

    # Retrieve stored abilities
    user_abilities = UserAbility.objects.filter(user_id=user_id)
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

    data = request.data
    categories = data.get('selected_categories')

    # Get all questions from the category
    all_questions = Question.objects.filter(category_id__in=categories)

    if not all_questions:
        return Response({'error': 'No questions available to generate an exam.'}, status=status.HTTP_404_NOT_FOUND)

    selected_questions = random.sample(list(all_questions), data.get('no_of_questions'))

    user = User.objects.get(supabase_user_id=supabase_uid)

    # Create a new exam instance for the authenticated user
    quiz = Assessment.objects.create(user=user, type='Quiz')

    quiz.questions.set(selected_questions)

    categories = set()  # Use a set to avoid duplicates
    for c in categories:
        category = Category.objects.get(name=c)
        categories.add(category)

    quiz.selected_categories.set(categories)
    quiz.save()

    # Format the questions and answers to send back to the frontend
    quiz_data = {
        'quiz_id': quiz.id,
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
def get_lessons(request):
    supabase_uid = get_user_id_from_token(request)

    if not supabase_uid:
        return Response({'error': 'User not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)

    # Fetch all category names
    categories = Category.objects.values_list('name', flat=True)

    return Response({'titles': list(categories)}, status=status.HTTP_200_OK)


# TODO
@api_view(['GET'])
def get_lesson(request, lesson_id):
    supabase_uid = get_user_id_from_token(request)

    if not supabase_uid:
        return Response({'error': 'User not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)

    return Response({'lesson_id': lesson_id}, status=status.HTTP_200_OK)


@api_view(['GET'])
def get_history(request):
    supabase_uid = get_user_id_from_token(request)

    if not supabase_uid:
        return Response({'error': 'User not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)

    user_id = User.objects.get(supabase_user_id=supabase_uid).id

    assessments = Assessment.objects.filter(user_id=user_id).prefetch_related('selected_categories')

    history = []
    for assessment in assessments:

        result = AssessmentResult.objects.get(assessment=assessment)

        if not result:
            continue

        item = {
            'assessment_id': assessment.id,
            'type': assessment.type,
            'score': result.score if result else None,
            'total_items': assessment.questions.count(),
            'time_taken': result.time_taken if result else None,
            'date_taken': assessment.created_at if result else None,
            'categories': [category.name for category in
                           assessment.selected_categories.all()]
        }

        history.append(item)

    return Response(history, status=status.HTTP_200_OK)


@api_view(['POST'])
def join_class(request):
    user_id = get_user_id_from_token(request)

    if not user_id:
        return Response({'error': 'User not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)

    # Get the user instance
    try:
        user = User.objects.get(supabase_user_id=user_id)
    except User.DoesNotExist:
        return Response({'error': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)

    data = request.data
    code = data.get('code')

    if not code:
        return Response({'error': 'Class code is required.'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        class_instance = Class.objects.get(class_code=code)  # Fetch class with the given code
    except Class.DoesNotExist:
        return Response({'error': 'Invalid class code.'}, status=status.HTTP_404_NOT_FOUND)

    if class_instance.students.filter(id=user_id).exists():
        return Response({'message': 'You are already a member of this class.'}, status=status.HTTP_200_OK)

    # Add the user to the class
    class_instance.students.add(user)

    return Response({'message': 'Successfully joined the class.'}, status=status.HTTP_200_OK)
