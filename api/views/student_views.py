from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from ..utils.supabase_client import get_supabase_client
import random, json
from ..models import User, Question, Assessment, Answer, AssessmentResult, Class, UserAbility
from collections import defaultdict
from ..ai.estimate_student_ability import estimate_student_ability_per_category
from ..ai.rl_agent import DQNAgent
from general_views import get_user_id_from_token
from django.shortcuts import get_object_or_404


@api_view(['GET'])
def take_exam(request):
    user_id = get_user_id_from_token(request)

    if not user_id:
        return Response({'error': 'User not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)

    # Get all questions from the database
    all_questions = Question.objects.all()

    if not all_questions:
        return Response({'error': 'No questions available to generate an exam.'}, status=status.HTTP_404_NOT_FOUND)

    selected_questions = random.sample(list(all_questions), 60)

    user = User.objects.get(supabase_user_id=user_id)

    # Create a new exam instance for the authenticated user
    exam = Assessment.objects.create(user=user, type='Exam')

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

@api_view(['POST'])
def submit_exam(request):
    user_id = get_user_id_from_token(request)

    if not user_id:
        return Response({'error': 'User not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)

    data = request.data

    exam_id = data['exam_id']

    # Retrieve the exam object; ensure that the exam belongs to the authenticated user
    exam = get_object_or_404(Assessment, id=exam_id)

    if exam.user.supabase_user_id != user_id:
        return Response({'error': 'You are not authorized to submit answers for this exam.'},
                        status=status.HTTP_403_FORBIDDEN)

    # Parse the request data
    data = request.data
    answers = data.get('answers', [])

    # Initialize variables for scoring, time, and category breakdown
    score = 0
    total_time_spent = 0
    overall_correct_answers = 0
    overall_wrong_answers = 0

    # Create an ExamResult object to store the exam results
    exam_result = AssessmentResult.objects.create(
        assessment=exam,
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
    exam_result.score = overall_correct_answers
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
        'overall_correct_answers': overall_correct_answers,
        'overall_wrong_answers': overall_wrong_answers,
        'total_questions': len(answers),
        'categories': categories,
    }

    return Response(result_data, status=status.HTTP_200_OK)

@api_view(['GET'])
def get_exam_results(request, exam_id):
    user_id = get_user_id_from_token(request)

    if not user_id:
        return Response({'error': 'User not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)

    # Retrieve the exam object; ensure that the exam belongs to the authenticated user
    exam = get_object_or_404(Assessment, id=exam_id)
    if exam.user.supabase_user_id != user_id:
        return Response({'error': 'You are not authorized to submit answers for this exam.'},
                        status=status.HTTP_403_FORBIDDEN)

    exam_results = AssessmentResult.objects.get(assessment=exam)

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

@api_view(['GET'])
def get_student_abilities(request):
    user_id = get_user_id_from_token(request)

    if not user_id:
        return Response({'error': 'User not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)

    # Query the UserAbility model for the user's abilities
    user_abilities = UserAbility.objects.filter(user_id=user_id)

    # Prepare a dictionary of categories and their associated ability levels
    abilities = {}
    for user_ability in user_abilities:
        abilities[user_ability.category.name] = user_ability.ability_level

    return Response(estimate_student_ability_per_category(user_id), status=status.HTTP_200_OK)


@api_view(['GET'])
def get_lessons_overall(request):

    user_id = get_user_id_from_token(request)

    if not user_id:
        return Response({'error': 'User not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)

    lesson_titles = {
        "titles": ['Basic Theory', 'Computer System', 'Technology Element', 'Development Technology', 'Project Management', 'Service Management', 'Business Strategy', 'System Strategy', 'Corporate and Legal Affairs']
    }

    return Response(lesson_titles, status=status.HTTP_200_OK)






@api_view(['GET'])
def take_quiz(request):
    user_id = get_user_id_from_token(request)
    data = request.data

    if not user_id:
        return Response({'error': 'User not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)

    categories = data.get('selected_categories')

    # Get all questions from the category
    all_questions = Question.objects.filter(category_id__in=categories)

    if not all_questions:
        return Response({'error': 'No questions available to generate an exam.'}, status=status.HTTP_404_NOT_FOUND)

    selected_questions = random.sample(list(all_questions), data.get('no_of_questions'))

    user = User.objects.get(supabase_user_id=user_id)

    # Create a new exam instance for the authenticated user
    quiz = Assessment.objects.create(user=user, type='Quiz')

    quiz.questions.set(selected_questions)
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