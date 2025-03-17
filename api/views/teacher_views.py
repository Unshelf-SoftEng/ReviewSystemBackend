from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from ..models import User, Class, UserAbility, Assessment, AssessmentResult, Question
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_datetime
from api.views.general_views import get_user_id_from_token


@api_view(['POST'])
def create_class(request):
    supabase_uid = get_user_id_from_token(request)

    if not supabase_uid:
        return Response({'error': 'User not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)

    user = User.objects.get(supabase_user_id=supabase_uid)

    if user.role != 'teacher':
        return Response({"error": "Only teachers can create classes"}, status=403)

    data = request.data
    class_name = data.get('class_name')

    if not class_name:
        return Response({"error": "Class name is required"}, status=400)

    # Create class and save students
    new_class = Class.objects.create(name=class_name, teacher=user)

    return Response({"message": "Class created successfully", "class_id": new_class.id, "class_code": new_class.class_code}, status=201)


@api_view(['GET'])
def get_classes(request):

    supabase_uid = get_user_id_from_token(request)

    if not supabase_uid:
        return Response({'error': 'User not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)

    user = User.objects.get(supabase_user_id=supabase_uid)

    if user.role != 'teacher':
        return Response({"error": "Only teachers can get classes"}, status=403)

    classes = Class.objects.filter(teacher=user)

    data_result = []

    for class_obj in classes:
        num_students = User.objects.filter(enrolled_class=class_obj).count()
        data_result.append({
            'class_id': class_obj.id,
            'class_name': class_obj.name,
            'number_of_students': num_students
        })

    # Return the data in the response
    return Response({"classes": data_result}, status=status.HTTP_200_OK)


@api_view(['GET'])
def get_class(request, class_id):
    supabase_uid = get_user_id_from_token(request)

    if not supabase_uid:
        return Response({'error': 'User not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)

    user = User.objects.get(supabase_user_id=supabase_uid)

    if user.role != 'teacher':
        return Response({"error": "Only teachers can get classes"}, status=403)

    teacher_class = Class.objects.get(id=class_id)
    students = [{'id': student.id, 'name': student.full_name} for student in teacher_class.students.all()]

    data_result = {
        'class_id': class_id,
        'class_name': teacher_class.name,
        'number_of_students': teacher_class.students.count(),
        'class_code': teacher_class.class_code,
        'students': students
    }

    return Response({"class": data_result}, status=status.HTTP_200_OK)


@api_view(['GET'])
def get_student_data(request, student_id):
    supabase_uid = get_user_id_from_token(request)

    if not supabase_uid:
        return Response({'error': 'User not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)

    teacher = get_object_or_404(User, supabase_user_id=supabase_uid)

    if teacher.role != 'teacher':
        return Response({"error": "Only teachers can access student data"}, status=status.HTTP_403_FORBIDDEN)

    student = get_object_or_404(User, id=student_id)

    if student.role != 'student':
        return Response({"error": "Student ID specified is not a student"}, status=status.HTTP_403_FORBIDDEN)

    user_abilities = UserAbility.objects.filter(user_id=student_id)
    stored_abilities = {user_ability.category.name: user_ability.ability_level for user_ability in user_abilities}

    assessments = Assessment.objects.filter(user_id=student_id).prefetch_related('selected_categories')

    history = []
    for assessment in assessments:
        result = AssessmentResult.objects.filter(assessment=assessment).first()  # Avoid exceptions

        if not result:
            continue

        item = {
            'assessment_id': assessment.id,
            'type': assessment.type,
            'score': result.score,
            'total_items': assessment.questions.count(),
            'time_taken': result.time_taken,
            'date_taken': assessment.created_at,
            'categories': [category.name for category in assessment.selected_categories.all()]
        }

        history.append(item)

    return Response({
        "name": student.full_name,
        "abilities": stored_abilities,
        "history": history
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
def get_all_questions(request):
    supabase_uid = get_user_id_from_token(request)

    if not supabase_uid:
        return Response({'error': 'User not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)

    teacher = get_object_or_404(User, supabase_user_id=supabase_uid)

    if teacher.role != 'teacher':
        return Response({"error": "Only teachers can access student data"}, status=status.HTTP_403_FORBIDDEN)

    questions = Question.objects.all()

    response_data = []
    for question in questions:
        question_data = {
            'question_id': question.id,
            'question_text': question.question_text,
            'category_name': question.category.name,
        }
        response_data.append(question_data)

    return Response(response_data, status=status.HTTP_200_OK)

@api_view(['POST'])
def create_quiz(request, class_id):
    supabase_uid = get_user_id_from_token(request)

    if not supabase_uid:
        return Response({'error': 'User not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)

    teacher = get_object_or_404(User, supabase_user_id=supabase_uid)

    if teacher.role != 'teacher':
        return Response({"error": "Only teachers can access student data"}, status=status.HTTP_403_FORBIDDEN)

    data = request.data
    question_source = data.get('question_source')
    questions = data.get('questions')

    if not question_source:
        return Response({'error': 'Question source not provided'}, status=status.HTTP_400_BAD_REQUEST)

    quiz = Assessment.objects.create(user=teacher)

    selected_categories = []
    selected_questions = []

    if question_source == "previous_exam":

        for question in questions:
            question_obj = Question.objects.get(id=question)
            selected_questions.append(question_obj)
            selected_categories.append(question_obj.category.id)

        quiz.selected_categories.set(selected_categories)
        quiz.questions.set(selected_questions)
        quiz.deadline = parse_datetime(data.get('deadline')) if data.get('deadline') else None
        quiz.no_of_questions = data.get('no_of_questions')
        quiz.status = "created"
        quiz.class_owner = Class.objects.get(id=class_id)
        quiz.save()

    elif question_source == "mixed":
        return Response({'message': 'AI-generated questions feature has not been implemented yet.'},
                        status=status.HTTP_501_NOT_IMPLEMENTED)
    else:
        return Response({'message': 'AI-generated questions feature has not been implemented yet.'},
                        status=status.HTTP_501_NOT_IMPLEMENTED)

    return Response({"message": "Quiz was successfully created"}, status=status.HTTP_200_OK)


@api_view(['GET'])
def get_all_quizzes(request, class_id):
    supabase_uid = get_user_id_from_token(request)

    if not supabase_uid:
        return Response({'error': 'User not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)

    teacher = get_object_or_404(User, supabase_user_id=supabase_uid)

    if teacher.role != 'teacher':
        return Response({"error": "Only teachers can access student data"}, status=status.HTTP_403_FORBIDDEN)

    class_obj = Class.objects.get(id=class_id)

    assessments = Assessment.objects.filter(class_owner=class_obj)

    quizzes_data = []

    for assessment in assessments:
        quiz_data = {
            "id": assessment.id,
            "name": assessment.name,
            "number_of_questions": assessment.questions.count(),
            "created_at": assessment.created_at,
            "deadline": assessment.deadline,
            "categories": list(assessment.selected_categories.values_list('name', flat=True))
        }
        quizzes_data.append(quiz_data)

    return Response(quizzes_data, status=status.HTTP_200_OK)