from pyasn1_modules.rfc2315 import data
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from ..models import User, Class, UserAbility, Assessment, AssessmentResult, Question, AssessmentProgress
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

    # Create initial assessment

    question_ids = [
        '24-A-1', '24-A-2', '24-A-3', '24-A-4', '24-A-5',
        '24-A-6', '24-A-7', '24-A-8', '24-A-9', '24-A-10',
        '24-A-11', '24-A-12', '24-A-13', '24-A-14', '24-A-15',
        '24-A-16', '24-A-17', '24-A-18', '24-A-19', '24-A-20',
        '24-A-21', '24-A-22', '24-A-23', '24-A-24', '24-A-25',
        '24-A-26', '24-A-27', '24-A-28', '24-A-29', '24-A-30',
        '24-A-31', '24-A-32', '24-A-33', '24-A-34', '24-A-35',
        '24-A-36', '24-A-37', '24-A-38', '24-A-39', '24-A-40',
        '24-A-41', '24-A-42', '24-A-43', '24-A-44', '24-A-45',
        '24-A-46', '24-A-47', '24-A-48', '24-A-49', '24-A-50',
        '24-A-51', '24-A-52', '24-A-53', '24-A-54', '24-A-55',
        '24-A-56', '24-A-57', '24-A-58', '24-A-59', '24-A-60',
    ]

    assessment = Assessment.objects.create(
        name='Initial Assessment',
        class_owner=new_class,
        type='exam',
        question_source='previous_exam',
        source='admin_generated',
        time_limit=8100,
        is_initial=True,
    )

    questions = Question.objects.filter(pk__in=question_ids)

    selected_categories = []
    for question in questions:
        if question.category not in selected_categories:
            selected_categories.append(question.category)

    assessment.selected_categories.set(selected_categories)
    assessment.questions.set(questions)

    return Response(
        {"message": "Class created successfully", "class_id": new_class.id, "class_code": new_class.class_code},
        status=201)


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
    print("Get Class was called with class_id:", class_id)  # Debugging line
    supabase_uid = get_user_id_from_token(request)

    if not supabase_uid:
        return Response({'error': 'User not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)

    user = User.objects.get(supabase_user_id=supabase_uid)

    if user.role != 'teacher':
        return Response({"error": "Only teachers can get classes"}, status=403)

    teacher_class = Class.objects.get(id=class_id)

    if teacher_class is None:
        return Response({"error": "Class not found."}, status=status.HTTP_404_NOT_FOUND)

    students_data = User.objects.filter(enrolled_class=teacher_class)

    students = []
    for student in students_data:
        students.append({
            'id': student.id,
            'name': student.full_name
        })

    data_result = {
        'class_id': class_id,
        'class_name': teacher_class.name,
        'number_of_students': students_data.count(),
        'class_code': teacher_class.class_code,
        'students': students
    }

    return Response({"class": data_result}, status=status.HTTP_200_OK)


@api_view(['GET'])
def view_initial_exam(request, class_id):
    print("View Initial Exam was called")
    supabase_uid = get_user_id_from_token(request)

    if not supabase_uid:
        return Response({'error': 'User not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)

    user = User.objects.get(supabase_user_id=supabase_uid)

    if user.role != 'teacher':
        return Response({"error": "Only teachers can get classes"}, status=status.HTTP_403_FORBIDDEN)

    class_owner = Class.objects.get(id=class_id)

    # Retrieve the exam object; ensure that the exam belongs to the authenticated user
    exam = get_object_or_404(Assessment, class_owner=class_owner, is_initial=True)

    exam_data = {
        'exam_id': exam.id,
        'is_open': exam.deadline is not None,
    }

    return Response(exam_data, status=status.HTTP_200_OK)


@api_view(['POST'])
def open_initial_exam(request, class_id):
    supabase_uid = get_user_id_from_token(request)

    if not supabase_uid:
        return Response({'error': 'User not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)

    user = User.objects.get(supabase_user_id=supabase_uid)

    if user.role != 'teacher':
        return Response({"error": "Only teachers can get classes"}, status=403)

    data = request.data

    deadline = data['deadline']

    class_owner = Class.objects.get(id=class_id)

    exam = Assessment.objects.get(class_owner=class_owner, is_initial=True)

    exam.deadline = deadline
    exam.save()

    return Response({'message': 'Initial Exam is Opened'}, status=status.HTTP_200_OK)


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

    user_ability = UserAbility.objects.filter(user_id=student_id)
    stored_abilities = {user_ability.category.name: user_ability.ability_level for user_ability in user_ability}

    assessment_results = AssessmentResult.objects.filter(user=student)

    history = []
    for assessment_result in assessment_results:
        assessment = assessment_result.assessment

        item = {
            'assessment_id': assessment.id,
            'type': assessment.type,
            'score': assessment_result.score,
            'total_items': assessment.questions.count(),
            'time_taken': assessment_result.time_taken,
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

    # Use select_related to minimize queries (joins category to Question)
    questions = Question.objects.select_related('category').values('id', 'question_text', 'category__name')

    return Response(list(questions), status=status.HTTP_200_OK)


@api_view(['POST'])
def create_quiz(request, class_id):
    print("Create Quiz was Called")
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

    class_owner = Class.objects.get(id=class_id)
    quiz = Assessment.objects.create(name=data.get('name'), class_owner=class_owner)

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
        quiz.type = "quiz"
        quiz.status = "created"
        quiz.source = "teacher_generated"
        quiz.save()

    elif question_source == "mixed":
        return Response({'message': 'AI-generated questions feature has not been implemented yet.'},
                        status=status.HTTP_501_NOT_IMPLEMENTED)
    else:
        return Response({'message': 'AI-generated questions feature has not been implemented yet.'},
                        status=status.HTTP_501_NOT_IMPLEMENTED)

    return Response({"message": "Quiz was successfully created"}, status=status.HTTP_200_OK)


@api_view(['GET'])
def get_class_assessments(request, class_id):
    print("Get All Quizzes was called")

    supabase_uid = get_user_id_from_token(request)

    if not supabase_uid:
        return Response({'error': 'User not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)

    teacher = get_object_or_404(User, supabase_user_id=supabase_uid)

    if teacher.role != 'teacher':
        return Response({"error": "Only teachers can access student data"}, status=status.HTTP_403_FORBIDDEN)

    class_obj = Class.objects.get(id=class_id)

    assessments = Assessment.objects.filter(class_owner=class_obj).order_by("-created_at")

    quizzes_data = []

    for assessment in assessments:
        quiz_data = {
            "id": assessment.id,
            "name": assessment.name,
            "type": assessment.type,
            "question_source": assessment.question_source,
            "number_of_questions": assessment.questions.count(),
            "created_at": assessment.created_at,
            "deadline": assessment.deadline,
            "categories": list(assessment.selected_categories.values_list('name', flat=True))

        }
        quizzes_data.append(quiz_data)

    return Response(quizzes_data, status=status.HTTP_200_OK)


@api_view(['GET'])
def get_assessment_data(request, assessment_id):
    supabase_uid = get_user_id_from_token(request)

    if not supabase_uid:
        return Response({'error': 'User not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)

    teacher = get_object_or_404(User, supabase_user_id=supabase_uid)

    if teacher.role != 'teacher':
        return Response({"error": "Only teachers can access assessment data"}, status=status.HTTP_403_FORBIDDEN)

    assessment = get_object_or_404(Assessment, id=assessment_id)

    questions_data = []
    for question in assessment.questions.all():
        questions_data.append({
            "id": question.id,
            "question_text": question.question_text,
            "choices": question.choices,
            "answer": question.correct_answer
        })

    response_data = {
        "id": assessment.id,
        "name": assessment.name,
        "type": assessment.type,
        "question_source": assessment.question_source,
        "source": assessment.source,
        "no_of_items": assessment.questions.count(),
        "questions": questions_data,
    }

    if assessment.deadline is not None:
        response_data["deadline"] = assessment.deadline

    return Response(response_data, status=status.HTTP_200_OK)


@api_view(['GET'])
def get_assessment_results(request, assessment_id):
    supabase_uid = get_user_id_from_token(request)

    if not supabase_uid:
        return Response({'error': 'User not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)

    teacher = get_object_or_404(User, supabase_user_id=supabase_uid)

    if teacher.role != 'teacher':
        return Response({"error": "Only teachers can access student results"}, status=status.HTTP_403_FORBIDDEN)

    assessment = get_object_or_404(Assessment, id=assessment_id)
    students = User.objects.filter(enrolled_class=assessment.class_owner)
    students_data = []
    total_score = 0

    for student in students:
        assessment_result = AssessmentResult.objects.filter(assessment=assessment, user=student).first()

        if assessment_result:
            students_data.append({
                "student_id": student.id,
                "student_name": student.full_name,
                "taken": True,
                "score": assessment_result.score
            })
            total_score += assessment_result.score
        else:
            students_data.append({
                "student_id": student.id,
                "student_name": student.full_name,
                "taken": False,
            })

    average_score = total_score / students.count() if students.exists() else 0

    return Response({
        "assessment_id": assessment.id,
        "assessment_name": assessment.name,
        "average_score": average_score,
        "students_data": students_data,
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
def update_assessment(request, assessment_id):
    supabase_uid = get_user_id_from_token(request)

    if not supabase_uid:
        return Response({'error': 'User not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)

    teacher = get_object_or_404(User, supabase_user_id=supabase_uid)

    if teacher.role != 'teacher':
        return Response({"error": "You are not authorized to access this link"}, status=status.HTTP_403_FORBIDDEN)

    questions = request.data.get('questions')
    assessment = get_object_or_404(Assessment, id=assessment_id)
    deadline = parse_datetime(request.data.get('deadline')) if request.data.get('deadline') else None
    assessment.deadline = deadline
    assessment.save()

    for question_data in questions:
        question = Question.objects.filter(id=question_data["id"]).first()

        if question:
            question.question_text = question_data["question_text"]
            question.choices = question_data["choices"]
            question.correct_answer = question_data["answer"]
            question.save()

    return Response({"message": "Quiz was successfully updated"}, status=status.HTTP_200_OK)


def delete_assessment(request, quiz_id):
    supabase_uid = get_user_id_from_token(request)

    if not supabase_uid:
        return Response({'error': 'User not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)

    teacher = get_object_or_404(User, supabase_user_id=supabase_uid)

    if teacher.role != 'teacher':
        return Response({"error": "Only teachers can access student data"}, status=status.HTTP_403_FORBIDDEN)

    assessment = get_object_or_404(Assessment, id=quiz_id)

    # Check for related AssessmentResult or AssessmentProgress
    has_results = AssessmentResult.objects.filter(assessment=assessment).exists()
    has_progress = AssessmentProgress.objects.filter(assessment=assessment).exists()

    if has_results or has_progress:
        return Response(
            {"error": "Cannot delete assessment because there are related results or progress records."},
            status=status.HTTP_400_BAD_REQUEST
        )

    assessment.delete()
    return Response({"success": "Assessment deleted successfully."}, status=status.HTTP_204_NO_CONTENT)