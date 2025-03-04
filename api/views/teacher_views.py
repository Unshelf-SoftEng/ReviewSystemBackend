from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from ..models import User, Class


from api.views.general_views import get_user_id_from_token

@api_view(['POST'])
def create_class(request):
    if request.method == 'POST':

        user_id = get_user_id_from_token(request)

        if not user_id:
            return Response({'error': 'User not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)

        data = request.data

        user = User.objects.get(supabase_user_id=user_id)

        if user.role != 'teacher':
            return Response({"error": "Only teachers can create classes"}, status=403)

        class_name = data.get('name')

        if not class_name:
            return Response({"error": "Class name is required"}, status=400)

        # Create class and save students
        new_class = Class.objects.create(name=class_name, teacher=user)

        return Response({"message": "Class created successfully", "class_id": new_class.id}, status=201)

    return Response({"error": "Invalid request method"}, status=405)


@api_view(['GET'])
def get_classes(request):
    user_id = get_user_id_from_token(request)

    if not user_id:
        return Response({'error': 'User not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)

    user = User.objects.get(supabase_user_id=user_id)

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
    if not class_id:
        return Response({'error': 'Class id is required'}, status=400)

    user_id = get_user_id_from_token(request)

    if not user_id:
        return Response({'error': 'User not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)

    user = User.objects.get(supabase_user_id=user_id)

    if user.role != 'teacher':
        return Response({"error": "Only teachers can get classes"}, status=403)

    teacher_class = Class.objects.get(id=class_id)
    student_names = [student.full_name for student in teacher_class.students.all()]

    data_result = {
        'class_id': class_id,
        'class_name': teacher_class.name,
        'number_of_students': teacher_class.students.count(),
        'class_code': teacher_class.class_code,
        'students': list(student_names)
    }

    return Response({"class": data_result}, status=status.HTTP_200_OK)


@api_view(['POST'])
def join_class(request):
    data = request.data

    # Step 1: Get the student based on the authentication (assuming you get user info from token)
    user_id = get_user_id_from_token(request)

    if not user_id:
        return Response({'error': 'User not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)

    user = User.objects.get(supabase_user_id=user_id)

    if user.role != 'student':
        return Response({"error": "Only students can join classes"}, status=403)

    try:
        teacher_class = Class.objects.get(class_code=data.get('class_code'))
    except Class.DoesNotExist:
        return Response({'error': 'Invalid class code.'}, status=status.HTTP_404_NOT_FOUND)

    # Step 3: Add the student to the class
    if user in teacher_class.students.all():
        return Response({'message': 'You are already enrolled in this class.'}, status=status.HTTP_400_BAD_REQUEST)

    teacher_class.students.add(user)  # Add student to the class's student list
    teacher_class.save()

    # Step 4: Return success response
    return Response({'message': 'Successfully joined the class.'}, status=status.HTTP_200_OK)








@api_view(['GET'])
def generate_quiz(request):
    user_id = get_user_id_from_token(request)
    data = request.data

    if not user_id:
        return Response({'error': 'User not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)
