from pyasn1_modules.rfc2315 import data
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from ..models import User, Class, UserAbility, Assessment, AssessmentResult, Question, AssessmentProgress, Lesson, \
    Chapter
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_datetime
from api.decorators import auth_required


@api_view(['GET'])
@auth_required("teacher")
def create_initial_assessment(request, class_id):
    user: User = request.user

    question_ids = [
        '24-A-01', '24-A-02', '24-A-03', '24-A-04', '24-A-05',
        '24-A-06', '24-A-07', '24-A-08', '24-A-09', '24-A-10',
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

    if Assessment.objects.filter(class_owner__id=class_id, is_initial=True).exists():
        return Response({'error': 'Initial Assessment already exists'}, status=status.HTTP_400_BAD_REQUEST)

    assessment = Assessment.objects.create(
        name='Initial Assessment',
        class_owner=Class.objects.get(pk=class_id),
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

    return Response({"message": "Assessment created"}, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@auth_required("teacher")
def create_class(request):
    user: User = request.user
    class_name = request.data.get('class_name')

    if not class_name:
        return Response({"error": "Class name is required"}, status=400)

    # Create class and save students
    new_class = Class.objects.create(name=class_name, teacher=user)

    # Create initial assessment

    question_ids = [
        '24-A-01', '24-A-02', '24-A-03', '24-A-04', '24-A-05',
        '24-A-06', '24-A-07', '24-A-08', '24-A-09', '24-A-10',
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
@auth_required("teacher")
def get_classes(request):
    user: User = request.user
    classes = Class.objects.filter(teacher=user)

    data_result = []

    for class_obj in classes:
        num_students = User.objects.filter(enrolled_class=class_obj).count()
        data_result.append({
            'class_id': class_obj.id,
            'class_name': class_obj.name,
            'number_of_students': num_students
        })

    return Response({"classes": data_result}, status=status.HTTP_200_OK)


@api_view(['GET'])
@auth_required("teacher")
def get_class(request, class_id):
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
@auth_required("teacher")
def view_initial_exam(request, class_id):
    class_owner = Class.objects.get(id=class_id)

    exam = get_object_or_404(Assessment, class_owner=class_owner, is_initial=True)

    exam_data = {
        'exam_id': exam.id,
        'is_open': exam.deadline is not None,
    }

    return Response(exam_data, status=status.HTTP_200_OK)


@api_view(['POST'])
@auth_required("teacher")
def open_initial_exam(request, class_id):
    deadline = request.data['deadline']
    class_owner = Class.objects.get(id=class_id)
    exam = Assessment.objects.get(class_owner=class_owner, is_initial=True)

    if exam.deadline is not None:
        return Response({'message': 'Initial Exam is already open.'}, status=status.HTTP_400_BAD_REQUEST)

    exam.deadline = deadline
    exam.save()

    return Response({'message': 'Initial Exam is Opened'}, status=status.HTTP_200_OK)


@api_view(['GET'])
@auth_required("teacher")
def get_student_data(request, student_id):
    student = get_object_or_404(User, id=student_id)

    if student.role != 'student':
        return Response({"error": "Student ID specified is not a student"}, status=status.HTTP_403_FORBIDDEN)

    user_ability = UserAbility.objects.filter(user_id=student_id)
    stored_abilities = {user_ability.category.name: user_ability.irt_ability for user_ability in user_ability}

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
@auth_required("teacher")
def get_all_questions(request):
    questions = Question.objects.select_related('category').values('id', 'question_text', 'category__name')

    return Response(list(questions), status=status.HTTP_200_OK)


@api_view(['POST'])
@auth_required("teacher")
def create_assessment(request, class_id):
    question_source = request.data.get('question_source')
    questions = request.data.get('questions')
    assessment_type = request.data.get('type', 'quiz') or 'quiz'

    if not question_source:
        return Response({'error': 'Question source not provided'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        class_obj = Class.objects.get(pk=class_id)
    except Class.DoesNotExist:
        return Response({'error': 'Class not found'}, status=status.HTTP_404_NOT_FOUND)

    assessment = Assessment.objects.create(
        name=request.data.get('name'),
        class_owner=class_obj
    )

    if question_source == "previous_exam":

        selected_questions = list(Question.objects.filter(id__in=questions))
        selected_categories = {q.category.id for q in selected_questions}
        assessment.selected_categories.set(selected_categories)
        assessment.questions.set(selected_questions)
        assessment.deadline = parse_datetime(request.data.get('deadline')) if request.data.get('deadline') else None
        assessment.no_of_questions = request.data.get('no_of_questions')
        assessment.type = assessment_type
        assessment.source = "teacher_generated"
        assessment.save()

    elif question_source == "mixed":
        return Response({'message': 'AI-generated questions feature has not been implemented yet.'},
                        status=status.HTTP_501_NOT_IMPLEMENTED)
    else:
        return Response({'message': 'AI-generated questions feature has not been implemented yet.'},
                        status=status.HTTP_501_NOT_IMPLEMENTED)

    return Response({"message": "Quiz was successfully created"}, status=status.HTTP_200_OK)


@api_view(['GET'])
@auth_required("teacher")
def get_class_assessments(request, class_id):
    assessments = Assessment.objects.filter(class_owner__id=class_id).order_by("-created_at")

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
@auth_required("teacher")
def get_assessment_data(request, assessment_id):
    assessment = get_object_or_404(Assessment.objects.prefetch_related("questions"), id=assessment_id)

    questions_data = list(
        assessment.questions.values("id", "question_text", "choices", "correct_answer")
    )

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
@auth_required("teacher")
def get_assessment_results(request, assessment_id):
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
@auth_required("teacher")
def update_assessment(request, assessment_id):
    questions = request.data.get("questions", [])
    assessment = get_object_or_404(Assessment, id=assessment_id)

    if "deadline" in request.data:
        assessment.deadline = parse_datetime(request.data["deadline"]) if request.data["deadline"] else None
        assessment.save(update_fields=["deadline"])

    question_ids = [q["id"] for q in questions]
    existing_questions = {q.id: q for q in Question.objects.filter(id__in=question_ids)}

    updated_questions = []
    for question_data in questions:
        question = existing_questions.get(question_data["id"])
        if question:
            question.question_text = question_data["question_text"]
            question.choices = question_data["choices"]
            question.correct_answer = question_data["answer"]
            updated_questions.append(question)

    # Bulk update all modified questions in one query
    if updated_questions:
        Question.objects.bulk_update(updated_questions, ["question_text", "choices", "correct_answer"])

    return Response({"message": "Quiz was successfully updated"}, status=status.HTTP_200_OK)


@api_view(['POST'])
@auth_required("teacher")
def delete_assessment(request, quiz_id):
    assessment = get_object_or_404(Assessment, id=quiz_id)
    has_results = AssessmentResult.objects.filter(assessment=assessment).exists()
    has_progress = AssessmentProgress.objects.filter(assessment=assessment).exists()

    if has_results or has_progress:
        return Response(
            {"error": "Cannot delete assessment because there are related results or progress records."},
            status=status.HTTP_400_BAD_REQUEST
        )

    assessment.delete()
    return Response({"success": "Assessment deleted successfully."}, status=status.HTTP_204_NO_CONTENT)


@api_view(['GET'])
@auth_required("teacher")
def get_lessons(request):
    lessons_data = list(Lesson.objects.values("id", "name"))
    return Response(lessons_data, status=status.HTTP_200_OK)


@api_view(['GET'])
@auth_required("teacher")
def get_lesson(request, lesson_id):
    lesson = get_object_or_404(
        Lesson.objects.prefetch_related(
            "chapters__sections"
        ),
        id=lesson_id
    )

    if lesson.is_locked:
        return Response(
            {'error': 'Lesson is currently locked. Please wait till the teacher opens it'},
            status=status.HTTP_403_FORBIDDEN
        )

    has_completed_assessment = AssessmentResult.objects.filter(assessment__lesson=lesson).exists()

    lesson_structure = [
        {
            "id": chapter.id,
            "chapter_number": chapter.number,
            "chapter_name": chapter.name,
            "is_main_chapter": chapter.is_main_chapter,
            "is_locked": chapter.is_locked,
            "structure": (
                [
                    {
                        "section_id": section.id,
                        "section_number": section.number,
                        "section_name": section.name,
                    }
                    for section in chapter.sections.all()
                ] + (
                    [{"type": "quiz", "title": f"Quiz for {chapter.name}"}] if chapter.is_main_chapter else []
                )
            ) if not chapter.is_locked else None
        }
        for chapter in lesson.chapters.all()
    ]

    lesson_structure.append({
        "type": "quiz",
        "title": "Final Lesson Quiz",
        "completed": has_completed_assessment
    })

    return Response({
        "id": lesson.id,
        "lesson_name": lesson.name,
        "structure": lesson_structure,
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@auth_required("teacher")
def get_chapter(request, lesson_id, chapter_id):
    chapter = get_object_or_404(
        Chapter.objects.prefetch_related("sections"), id=chapter_id
    )

    if chapter.is_locked:
        return Response(
            {'error': 'Chapter is currently locked. Please wait till the teacher opens it'},
            status=status.HTTP_403_FORBIDDEN
        )

    chapter_data = {
        "id": chapter.id,
        "chapter_number": chapter.number,
        "chapter_name": chapter.name,
        "sections": [
            {
                "id": section.id,
                "number": section.number,
                "title": section.name,
                "content": section.content,
            }
            for section in chapter.sections.all()
        ]
    }

    return Response(chapter_data, status=status.HTTP_200_OK)


@api_view(['GET'])
@auth_required("teacher")
def get_lesson_quiz(request, class_id, lesson_id):
    students = User.objects.filter(enrolled_class_id=class_id)
    lesson = get_object_or_404(Lesson, id=lesson_id)
    assessments = Assessment.objects.filter(lesson=lesson, created_by__in=students)
    assessment_results = AssessmentResult.objects.filter(assessment__in=assessments).select_related("assessment")
    assessment_results_lookup = {ar.user_id: ar for ar in assessment_results}

    students_data = []
    total_score = 0
    student_count = students.count()

    for student in students:
        assessment_result = assessment_results_lookup.get(student.id)

        if assessment_result:
            question_count = assessment_result.assessment.questions.count()
            score_pct = (assessment_result.score / question_count) * 100 if question_count else 0
            students_data.append({
                "student_id": student.id,
                "student_name": student.full_name,
                "taken": True,
                "score_percentage": round(score_pct, 2)
            })
            total_score += score_pct
        else:
            students_data.append({
                "student_id": student.id,
                "student_name": student.full_name,
                "taken": False,
            })

    average_score = total_score / student_count if student_count > 0 else 0

    return Response({
        "lesson_id": lesson_id,
        "lesson_name": lesson.name,
        "average_percentage": round(average_score, 2),
        "students_data": students_data,
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@auth_required("teacher")
def get_chapter_quiz(request, class_id, chapter_id):
    chapter = get_object_or_404(Chapter.objects.select_related("lesson"), id=chapter_id)
    students = User.objects.filter(enrolled_class_id=class_id)
    assessments = Assessment.objects.filter(chapter=chapter, created_by__in=students)
    assessment_results = AssessmentResult.objects.filter(assessment__in=assessments).select_related("assessment")
    assessment_results_lookup = {ar.user_id: ar for ar in assessment_results}

    students_data = []
    total_score = 0
    student_count = students.count()

    for student in students:
        assessment_result = assessment_results_lookup.get(student.id)

        if assessment_result:
            question_count = assessment_result.assessment.questions.count()
            score_pct = (assessment_result.score / question_count) * 100 if question_count else 0

            students_data.append({
                "student_id": student.id,
                "student_name": student.full_name,
                "taken": True,
                "score_percentage": round(score_pct, 2)
            })
            total_score += score_pct
        else:
            students_data.append({
                "student_id": student.id,
                "student_name": student.full_name,
                "taken": False,
            })

    average_score = total_score / student_count if student_count > 0 else 0

    return Response({
        "chapter_id": chapter.id,
        "chapter_name": chapter.name,
        "lesson_name": chapter.lesson.name,
        "average_percentage": round(average_score, 2),
        "students_data": students_data,
    }, status=status.HTTP_200_OK)