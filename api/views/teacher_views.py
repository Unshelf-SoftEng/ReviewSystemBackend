from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from ..models import User, Class, UserAbility, Assessment, AssessmentResult
from django.shortcuts import get_object_or_404

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
        num_students = class_obj.students.count()  # Assuming you have a related field `students` in the Class model
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
