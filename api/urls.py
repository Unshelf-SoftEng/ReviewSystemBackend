from django.urls import path
from .views import *

urlpatterns = [

    # General Views
    path('register/', register_user, name='register_user'),
    path('login/', login_user, name='login_user'),

    path('logout/', logout_user, name='logout_user'),

    path('refresh-token/', refresh_token, name='refresh_token'),

    path('profile/', get_user_details, name='get_user_details'),

    path('update-password/', update_password, name='update_password'),

    # Student Views

    path('student/class', get_class, name='get_class'),

    path('student/class/join', join_class, name='join_class'),

    path('student/initial-exam', get_initial_exam, name='get_initial_exam'),

    path('student/take-initial-exam', take_initial_exam, name='take_initial_exam'),

    path('student/initial-exam-taken', initial_exam_taken, name='initial_exam_taken'),

    path('student/exam/take', take_exam, name='take_exam'),

    path('student/exam/<exam_id>/submit', submit_exam, name='submit_answers'),

    path('student/exam/<exam_id>', get_exam_results, name='get_exam_results'),

    path('student/ability', get_ability, name='get_student_abilities'),

    path('student/history', get_history, name='get_student_history'),

    path('student/quiz/take', take_quiz, name='take_quiz'),

    path('student/quiz/<quiz_id>/submit', submit_exam, name='submit_quiz'),

    path('student/quiz/take-lesson-quiz', take_lesson_quiz, name='take_lesson_quiz'),

    path('student/class/assessments', get_class_assessments, name='get_class_quizzes'),

    path('student/quiz/<quiz_id>', get_exam_results, name='get_quiz_results'),




    #Lessons
    path('lessons', get_lessons_overall, name='get_lessons_overall'),

    path('lessons/<lesson_id>/update_progress', update_lesson_progress, name='update_lesson_progress'),

    path('lessons/<lesson_id>', get_lesson, name='get_lesson'),



    # Teacher Views

    path('teacher/class', get_classes, name='get_classes'),

    path('teacher/class/create', create_class, name='create_class'),

    path('teacher/class/student/<student_id>', get_student_data, name='get_student_data'),

    path('teacher/class/<class_id>/view-initial-exam', view_initial_exam, name='get_initial_exam'),

    path('teacher/class/<class_id>/open-initial-exam', open_initial_exam, name='open_initial_exam'),

    path('teacher/get_questions', get_all_questions, name='get_all_questions'),

    path('teacher/class/<class_id>/create-quiz', create_quiz, name='create_quiz'),

    path('teacher/class/<class_id>/quiz', get_all_quizzes, name='get_all_quizzes'),

    path('teacher/class/<class_id>', get_class, name='get_class'),

]
