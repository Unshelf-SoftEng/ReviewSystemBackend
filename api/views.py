from rest_framework import status
from rest_framework.decorators import api_view
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from .utils.supabase_client import get_supabase_client
from .models import User, Question, Exam, Answer, ExamResult
import random, json
from collections import defaultdict


# Disable CSRF protection for this view (use cautiously)
@csrf_exempt
@api_view(['POST'])
def register_user(request):
    if request.method == 'POST':
        # Parse data from the request
        data = request.data  # Automatically parses JSON into a dictionary
        email = data.get('email')
        password = data.get('password')
        first_name = data.get('first_name')
        last_name = data.get('last_name')
        role = data.get('role')

        supabase = get_supabase_client()

        # Register the user with Supabase Auth
        try:
            # Supabase registration call
            auth_response = supabase.auth.sign_up({
                'email': email,
                'password': password,
                'options': {
                    'email_redirect_to': 'https://localhost:3000/login/',
                }
            })

            # Store user in the local database (PostgresSQL)
            new_user = User(
                supabase_user_id=auth_response.user.id,
                email=email,
                first_name=first_name,
                last_name=last_name,
                role=role,
            )
            new_user.save()

            # Return success response
            return Response({'message': 'User registered successfully!'}, status=status.HTTP_201_CREATED)
        except Exception as e:

            if "already exists" in str(e).lower():
                return Response({'error': 'Email already registered'}, status=status.HTTP_400_BAD_REQUEST)
            return Response({'error': f'Error: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)


# Login view (still incomplete, but here is the structure)
@api_view(['POST'])
@csrf_exempt
def login_user(request):
    if request.method == 'POST':
        # Parse data from the request
        data = request.data  # Automatically parses JSON into a dictionary
        email = data.get('email')
        password = data.get('password')

        supabase = get_supabase_client()

        try:
            # Authenticate user with Supabase
            auth_response = supabase.auth.sign_in_with_password({
                'email': email,
                'password': password
            })

            user = User.objects.get(supabase_user_id=auth_response.user.id)
            role = user.role

            # Return success response with role information
            return Response({
                'message': 'Login successful',
                'jwt_token': auth_response.session.access_token,
                'role': role
            }, status=status.HTTP_200_OK)

        except Exception as e:

            if "invalid login credentials" in str(e).lower():
                return Response({'error': 'Email or Password is incorrect'}, status=status.HTTP_400_BAD_REQUEST)

            return Response({'error': f'Error: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)


# def reset_password(request):
#     data = request.data  # Automatically parses JSON into a dictionary
#     email = data.get('email')
#     get_supabase_client().reset_password_email(
#         email=email,
#         options={'redirect_to': 'https://localhost:3000/update_password/'}
#     )
#
# def update_password(request):
#     data = request.data
#
#     password = data.get('password')
#     get_supabase_client().update_user({'password': password})


def get_user_id_from_token(request):
    """Helper function to extract the user ID from the Supabase JWT token."""
    token = request.headers.get('Authorization')
    if not token:
        return None
    token = token.split("Bearer ")[-1]

    try:
        response = get_supabase_client().auth.get_user(jwt=token)
        return response.user.id
    except Exception as e:
        print(str(e))
        return None


@api_view(['GET'])
@csrf_exempt
def take_exam(request):
    user_id = get_user_id_from_token(request)

    if not user_id:
        return Response({'error': 'User not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)

    # Get all questions from the database
    all_questions = Question.objects.all()

    if not all_questions:
        return Response({'error': 'No questions available to generate an exam.'}, status=status.HTTP_404_NOT_FOUND)

    selected_questions = random.sample(list(all_questions), 5)

    user = User.objects.get(supabase_user_id=user_id)

    # Create a new exam instance for the authenticated user
    exam = Exam.objects.create(user=user)

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
                'choices': question.choices
            }
            for question in selected_questions
        ]
    }

    return Response(exam_data, status=status.HTTP_200_OK)


@api_view(['GET'])
def get_exam(request, exam_id):
    user_id = get_user_id_from_token(request)

    if not user_id:
        return Response({'error': 'User not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)

    # Get the exam or return a 404 if not found
    exam = get_object_or_404(Exam, id=exam_id)

    # Prepare exam data, including questions
    exam_data = {
        'exam_id': exam.id,
        'questions': [
            {
                'question_id': question.id,
                'image_url': question.image_url,
                'question_text': question.question_text,
                'choices': json.dumps(question.choices)
            }
            for question in exam.questions.all()
        ]
    }

    # Return the formatted response
    return Response(exam_data, status=status.HTTP_200_OK)


@api_view(['POST'])
@csrf_exempt
def submit_answers(request, exam_id):
    user_id = get_user_id_from_token(request)
    if not user_id:
        return Response({'error': 'User not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)

    # Retrieve the exam object; ensure that the exam belongs to the authenticated user
    exam = get_object_or_404(Exam, id=exam_id)
    if exam.user.supabase_user_id != user_id:
        return Response({'error': 'You are not authorized to submit answers for this exam.'}, status=status.HTTP_403_FORBIDDEN)

    # Parse the request data
    data = request.data
    answers = data.get('answers', [])

    # Initialize variables for scoring, time, and category breakdown
    score = 0
    total_time_spent = 0
    overall_correct_answers = 0
    overall_wrong_answers = 0

    # Create an ExamResult object to store the exam results
    exam_result = ExamResult.objects.create(
        exam=exam,
        score=score,
        time_taken=total_time_spent
    )

    # Track correct and wrong answers by category
    category_stats = defaultdict(lambda: {'correct_answers': 0, 'wrong_answers': 0, 'total_questions': 0})

    # Loop through the answers and validate each one
    for answer_data in answers:
        question_id = answer_data.get('question_id')
        chosen_answer = answer_data.get('answer')
        time_spent = answer_data.get('time_spent')

        # Get the corresponding question
        question = get_object_or_404(Question, id=question_id)

        # Check if the chosen answer is correct
        is_correct = chosen_answer == question.correct_answer

        # Update category stats
        category = question.category
        category_stats[category.name]['total_questions'] += 1
        if is_correct:
            category_stats[category.name]['correct_answers'] += 1
            overall_correct_answers += 1
            score += 1  # Increment score if correct
        else:
            category_stats[category.name]['wrong_answers'] += 1
            overall_wrong_answers += 1

        # Create Answer object for tracking the answer details
        Answer.objects.create(
            exam_result=exam_result,
            question=question,
            time_spent=time_spent,
            chosen_answer=chosen_answer,
            is_correct=is_correct
        )

        # Accumulate total time spent
        total_time_spent += time_spent

    # Create an ExamResult object to store the exam results
    exam_result.score = total_time_spent
    exam_result.time_taken = total_time_spent

    exam_result.save()

    # Prepare the categories breakdown in the response
    categories = [
        {
            'category_name': category_name,
            'total_questions': stats['total_questions'],
            'correct_answers': stats['correct_answers'],
            'wrong_answers': stats['wrong_answers'],
        }
        for category_name, stats in category_stats.items()
    ]

    # Prepare the response data
    result_data = {
        'exam_id': exam.id,
        'student_id': user_id,
        'total_time_taken_seconds': total_time_spent,
        'score': score,
        'categories': categories,
        'overall_correct_answers': overall_correct_answers,
        'overall_wrong_answers': overall_wrong_answers,
        'total_questions': len(answers)  # Total number of questions answered
    }

    return Response(result_data, status=status.HTTP_200_OK)

@api_view(['GET'])
def get_exam_results(request, exam_id):

    user_id = get_user_id_from_token(request)
    if not user_id:
        return Response({'error': 'User not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)

    # Retrieve the exam object; ensure that the exam belongs to the authenticated user
    exam = get_object_or_404(Exam, id=exam_id)
    if exam.user.supabase_user_id != user_id:
        return Response({'error': 'You are not authorized to submit answers for this exam.'},
                        status=status.HTTP_403_FORBIDDEN)

    exam_results = ExamResult.objects.get(exam=exam)

    answers = Answer.objects.filter(exam_result=exam_results)

    overall_correct_answers = 0
    overall_wrong_answers = 0
    category_stats = defaultdict(lambda: {'total_questions': 0, 'correct_answers': 0, 'wrong_answers': 0})

    for answer in answers:

        category_name = answer.question.category.name

        category_stats[category_name]['total_questions'] += 1
        if answer.is_correct:
            category_stats[category_name]['correct_answers'] += 1
            overall_correct_answers += 1
        else:
            category_stats[category_name]['wrong_answers'] += 1
            overall_wrong_answers += 1

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
        'student_id': user_id,
        'total_time_taken_seconds': exam_results.time_taken,
        'score': exam_results.score,
        'categories': categories,
        'overall_correct_answers': overall_correct_answers,
        'overall_wrong_answers': overall_wrong_answers,
        'total_questions': len(answers),
    }

    return Response(result_data, status=status.HTTP_200_OK)
