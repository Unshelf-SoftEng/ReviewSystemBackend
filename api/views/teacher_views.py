from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_datetime
from django.db.models import Count, Q, Avg, Max, Prefetch
from api.models import User, Class, UserAbility, Assessment, AssessmentResult, Question, Lesson, Chapter, Answer
from api.decorators import auth_required
import os
from api.ai.estimate_student_ability import estimate_ability_irt, estimate_ability_elo, estimate_ability_elo_time


@api_view(['GET'])
@auth_required("teacher")
def create_initial_assessment(request, class_id):
    file_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "question_ids.txt")
    try:
        with open(file_path, "r") as file:
            question_ids = [line.strip() for line in file if line.strip()]
    except FileNotFoundError:
        return Response({'error': 'Question ID file not found'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

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

    new_class = Class.objects.create(name=class_name, teacher=user)

    file_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "question_ids.txt")
    try:
        with open(file_path, "r") as file:
            question_ids = [line.strip() for line in file if line.strip()]
    except FileNotFoundError:
        return Response({'error': 'Question ID file not found'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    if Assessment.objects.filter(class_owner=new_class, is_initial=True).exists():
        return Response({'error': 'Initial Assessment already exists'}, status=status.HTTP_400_BAD_REQUEST)

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

    response_data = []

    for class_obj in classes:
        num_students = User.objects.filter(enrolled_class=class_obj).count()
        response_data.append({
            'class_id': class_obj.id,
            'class_name': class_obj.name,
            'number_of_students': num_students
        })

    return Response({"classes": response_data}, status=status.HTTP_200_OK)


@api_view(['GET'])
@auth_required("teacher")
def get_class(request, class_id):
    user: User = request.user
    class_obj = get_object_or_404(Class, id=class_id)

    if class_obj.teacher != user:
        return Response({"error": "Cannot access class that was not created by the teacher"}, status=status.HTTP_200_OK)

    students_data = User.objects.filter(enrolled_class=class_obj)

    students = []
    for student in students_data:
        students.append({
            'id': student.id,
            'name': student.full_name
        })

    data_result = {
        'class_id': class_id,
        'class_name': class_obj.name,
        'number_of_students': students_data.count(),
        'class_code': class_obj.class_code,
        'students': students
    }

    return Response({"class": data_result}, status=status.HTTP_200_OK)


@api_view(['GET'])
@auth_required("teacher")
def view_initial_exam(request, class_id):
    exam = get_object_or_404(Assessment, class_owner__id=class_id, is_initial=True)

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

    exam = get_object_or_404(Assessment, class_owner=class_owner, is_initial=True)

    if exam.deadline is not None:
        return Response({'message': 'Initial Exam is already open.'}, status=status.HTTP_400_BAD_REQUEST)

    exam.deadline = deadline
    exam.save()

    return Response({'message': 'Initial Exam is Opened'}, status=status.HTTP_200_OK)


@api_view(['GET'])
@auth_required("teacher")
def get_student_data(request, student_id):
    student = get_object_or_404(User, id=student_id, role='student')
    user_ability = UserAbility.objects.filter(user_id=student_id)
    stored_abilities = {user_ability.category.name: user_ability.irt_ability for user_ability in user_ability}

    assessment_results = AssessmentResult.objects.filter(user=student).prefetch_related("assessment")

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
    questions = Question.objects.select_related('category').values('id', 'question_text', 'image_url', 'choices',
                                                                   'category__name')

    return Response(list(questions), status=status.HTTP_200_OK)


@api_view(['POST'])
@auth_required("teacher")
def create_assessment(request, class_id):
    user: User = request.user
    class_obj = get_object_or_404(Class, id=class_id)

    if class_obj.teacher != user:
        return Response({"error": "Teacher cannot create quiz to class it didn't create"},
                        status=status.HTTP_400_BAD_REQUEST)

    question_source = request.data.get('question_source')
    questions = request.data.get('questions')
    assessment_type = request.data.get('type', 'quiz') or 'quiz'

    if not question_source:
        return Response({'error': 'Question source not provided'}, status=status.HTTP_400_BAD_REQUEST)

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
    assessments = Assessment.objects.filter(
        class_owner__id=class_id,
        is_active=True
    ).exclude(
        source="lesson_generated"
    ).order_by("-created_at")

    assessments_data = []

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
        assessments_data.append(quiz_data)

    return Response(assessments_data, status=status.HTTP_200_OK)


@api_view(['GET'])
@auth_required("teacher")
def get_assessment_data(request, assessment_id):
    assessment = get_object_or_404(
        Assessment.objects.prefetch_related("questions"),
        id=assessment_id,
        is_active=True
    )

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


import time
from django.db import connection
from django.db import reset_queries


@api_view(['GET'])
@auth_required("teacher")
def get_assessment_results_students(request, assessment_id):
    assessment = get_object_or_404(
        Assessment.objects.select_related('class_owner'),
        id=assessment_id,
        is_active=True
    )

    section_start = time.time()
    students = User.objects.filter(
        enrolled_class=assessment.class_owner
    ).select_related('enrolled_class')
    student_ids = list(students.values_list('id', flat=True))

    results_stats = AssessmentResult.objects.filter(
        assessment=assessment
    ).values('user_id').annotate(
        score=Max('score'),
        time_taken=Max('time_taken'),
        total_answers=Count('answers'),
        correct=Count('answers', filter=Q(answers__is_correct=True)),
        wrong=Count('answers', filter=Q(answers__is_correct=False)),
        blank=Count('answers', filter=Q(answers__chosen_answer=''))
    )
    results_dict = {stat['user_id']: stat for stat in results_stats}

    students_data = []
    total_score = 0
    students_with_results = 0

    for student in students:
        stat = results_dict.get(student.id)
        if stat:
            students_data.append({
                "student_id": student.id,
                "name": student.full_name,
                "taken": True,
                "time_spent": stat['time_taken'],
                "correct": stat['correct'],
                "wrong": stat['wrong'],
                "blank": stat['blank'],
                "skipped": assessment.questions.count() - stat['total_answers'],
            })
            total_score += stat['score']
            students_with_results += 1
        else:
            students_data.append({
                "student_id": student.id,
                "name": student.full_name,
                "taken": False
            })

    response_data = {
        "assessment_id": assessment.id,
        "assessment_name": assessment.name,
        "total_students": len(student_ids),
        "students_taken": students_with_results,
        "average_score": round(total_score / students_with_results) if students_with_results else 0,
        "students_data": students_data,
    }

    return Response(response_data, status=status.HTTP_200_OK)


@api_view(['GET'])
@auth_required("teacher")
def get_assessment_results_questions(request, assessment_id):
    assessment = get_object_or_404(
        Assessment.objects.prefetch_related('questions'),
        id=assessment_id,
        is_active=True
    )

    student_ids = User.objects.filter(
        enrolled_class=assessment.class_owner
    ).values_list('id', flat=True)


    # student_scores = {}
    # for student_id in student_ids:
    #     total_score = Answer.objects.filter(
    #         assessment_result__assessment=assessment,
    #         assessment_result__user_id=student_id,
    #         is_correct=True
    #     ).count()
    #     student_scores[student_id] = total_score

    # sorted_scores = sorted(student_scores.items(), key=lambda x: x[1], reverse=True)
    # num_students = len(sorted_scores)
    # upper_cutoff = int(num_students * 0.25)
    # lower_cutoff = int(num_students * 0.75)

    # upper_group = [x[0] for x in sorted_scores[:upper_cutoff]]
    # lower_group = [x[0] for x in sorted_scores[lower_cutoff:]]

    questions_data = []
    count = 1
    for question in assessment.questions.all():
        count += 1

        # Get stats for all students
        stats = Answer.objects.filter(
            question=question,
            assessment_result__assessment=assessment,
            assessment_result__user_id__in=student_ids
        ).aggregate(
            avg_time=Avg('time_spent'),
            total=Count('pk'),
            a=Count('pk', filter=Q(chosen_answer=question.choices['a'])),
            b=Count('pk', filter=Q(chosen_answer=question.choices['b'])),
            c=Count('pk', filter=Q(chosen_answer=question.choices['c'])),
            d=Count('pk', filter=Q(chosen_answer=question.choices['d'])),
            blank=Count('pk', filter=Q(chosen_answer='')),
            correct=Count('pk', filter=Q(is_correct=True)),
        )

        # upper_correct = Answer.objects.filter(
        #     question=question,
        #     assessment_result__assessment=assessment,
        #     assessment_result__user_id__in=upper_group,
        #     is_correct=True
        # ).count()
        #
        # lower_correct = Answer.objects.filter(
        #     question=question,
        #     assessment_result__assessment=assessment,
        #     assessment_result__user_id__in=lower_group,
        #     is_correct=True
        # ).count()
        #
        # upper_proportion = upper_correct / len(upper_group) if upper_group else 0
        # lower_proportion = lower_correct / len(lower_group) if lower_group else 0
        # # upper_percent = upper_proportion * 100 if upper_proportion else 0
        # # lower_percent = lower_proportion * 100 if lower_proportion else 0
        # discrimination = upper_proportion - lower_proportion
        # question.discrimination = discrimination
        # question.save()

        questions_data.append({
            "question_id": question.id,
            "question_txt": question.question_text,
            'choices': question.choices,
            "answer": question.correct_answer,
            "avg_time_seconds": stats['avg_time'],
            "answer_choices": {
                "a": stats['a'],
                "b": stats['b'],
                "c": stats['c'],
                "d": stats['d'],
                "blank": stats['blank'],
                "skipped": len(student_ids) - stats['total'],
            },
            "correct_answers": stats['correct'],
            "wrong_answers": stats['total'] - stats['correct'],
            # "percent_correct": stats['correct'] / stats['total'] * 100 if stats['total'] else 0,
            # "discrimination": discrimination,
        })

    return Response({
        "assessment_id": assessment.id,
        "assessment_name": assessment.name,
        "total_students": len(student_ids),
        "questions_data": questions_data
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@auth_required("teacher")
def update_assessment(request, assessment_id):
    assessment = get_object_or_404(Assessment, id=assessment_id, is_active=True)

    questions = request.data.get("questions", [])

    if "deadline" in request.data:
        print("Deadline", request.data["deadline"])
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

    if updated_questions:
        Question.objects.bulk_update(updated_questions, ["question_text", "choices", "correct_answer"])

    return Response({"message": "Quiz was successfully updated"}, status=status.HTTP_200_OK)


@api_view(['POST'])
@auth_required("teacher")
def delete_assessment(request, assessment_id):
    assessment = get_object_or_404(
        Assessment,
        id=assessment_id,
    )
    assessment.is_active = False
    assessment.save(update_fields=["is_active"])
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
        Lesson.objects.prefetch_related("chapters__sections"),
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
def get_lesson_quiz_data(request, class_id, lesson_id):
    students = User.objects.filter(enrolled_class_id=class_id)
    lesson = get_object_or_404(Lesson, id=lesson_id)
    assessments = Assessment.objects.filter(lesson=lesson, class_owner__id=class_id, is_active=True)
    assessment_results = AssessmentResult.objects.filter(assessment__in=assessments, user__in=students).select_related(
        "assessment")
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
    assessments = Assessment.objects.filter(chapter=chapter, class_owner_id=class_id)
    assessment_results = AssessmentResult.objects.filter(assessment__in=assessments, user__in=students).select_related(
        "assessment")
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


@api_view(['GET'])
@auth_required("teacher")
def estimate_ability_students(request, class_id):
    students = User.objects.filter(enrolled_class__id=class_id)
    count = 1
    response_data = []
    for student in students:
        print("Estimating Ability of ", student.full_name)
        print("Count: ", count)
        count += 1

        assessment = Assessment.objects.filter(class_owner_id=class_id, is_initial=True).first()
        if AssessmentResult.objects.filter(assessment=assessment, user=student).exists():
            # estimate_ability_irt(student.id)
            estimate_ability_elo(student.id)
            # estimate_ability_elo_time(student.id)

            user_abilities = UserAbility.objects.filter(user_id=student.id)
            irt_abilities = {
                user_ability.category.name: user_ability.irt_ability for user_ability in user_abilities
            }

            elo_abilities = {
                user_ability.category.name: user_ability.elo_ability for user_ability in user_abilities
            }

            elo_time_abilities = {
                user_ability.category.name: user_ability.elo_time_ability for user_ability in user_abilities
            }

            response_data.append({
                "id": student.id,
                "name": student.full_name,
                "irt": irt_abilities,
                "elo": elo_abilities,
                "elo_time": elo_time_abilities
            })

    return Response(response_data, status=status.HTTP_200_OK)
