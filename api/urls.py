from django.urls import path
from .views import teacher_views, student_views, general_views

urlpatterns = [

    # General Views
    path('register/', general_views.register_user, name='register_user'),
    path('login/', general_views.login_user, name='login_user'),

    path('logout/', general_views.logout_user, name='logout_user'),

    path('refresh-token/', general_views.refresh_token, name='refresh_token'),

    path('profile/', general_views.get_user_details, name='get_user_details'),

    path('update-password/', general_views.update_password, name='update_password'),

    # Student Views

    path('student/class', student_views.get_class, name='get_student_class'),

    path('student/class/join', student_views.join_class, name='join_class'),

    path('student/initial-exam', student_views.get_initial_exam, name='get_initial_exam'),

    path('student/take-initial-exam', student_views.take_initial_exam, name='take_initial_exam'),

    path('student/initial-exam-taken', student_views.initial_exam_taken, name='initial_exam_taken'),

    path('student/assessment/<int:assessment_id>/time-limit', student_views.check_time_limit, name='check_time_limit'),

    path('student/exam/take', student_views.take_exam, name='take_exam'),

    path('student/exam/<assessment_id>/submit', student_views.submit_assessment, name='submit_exam'),

    path('student/exam/<assessment_id>', student_views.get_exam_results, name='get_exam_results'),

    path('student/ability', student_views.get_ability, name='get_student_abilities'),

    path('student/history', student_views.get_history, name='get_student_history'),

    path('student/quiz/take', student_views.create_student_quiz, name='take_quiz'),

    path('student/quiz/<assessment_id>/submit', student_views.submit_assessment, name='submit_quiz'),

    path('student/quiz/<assessment_id>', student_views.get_exam_results, name='get_quiz_results'),

    path('student/quiz/take-lesson-quiz', student_views.take_lesson_quiz, name='take_lesson_quiz'),

    path('student/class/assessments', student_views.get_class_assessments, name='get_class_quizzes'),

    path('student/quiz/<quiz_id>', student_views.get_exam_results, name='get_quiz_results'),




    #Lessons
    path('lessons', general_views.get_lessons_overall, name='get_lessons_overall'),

    path('lessons/<lesson_id>/update_progress', general_views.update_lesson_progress, name='update_lesson_progress'),

    path('lessons/<lesson_id>', general_views.get_lesson, name='get_lesson'),



    # Teacher Views

    path('teacher/classes', teacher_views.get_classes, name='get_classes'),

    path('teacher/class/create', teacher_views.create_class, name='create_class'),

    path('teacher/class/student/<student_id>', teacher_views.get_student_data, name='get_student_data'),

    path('teacher/get_questions', teacher_views.get_all_questions, name='get_all_questions'),

    path('teacher/class/<class_id>/create-quiz', teacher_views.create_quiz, name='create_quiz'),

    path('teacher/class/<class_id>/view-initial-exam', teacher_views.view_initial_exam, name='get_initial_exam'),

    path('teacher/class/<class_id>/open-initial-exam', teacher_views.open_initial_exam, name='open_initial_exam'),

    path('teacher/class/<class_id>/assessments', teacher_views.get_class_assessments, name='get_all_quizzes'),

    path('teacher/assessment/<assessment_id>/results', teacher_views.get_assessment_results, name='get_assessment_results'),

    path('teacher/assessment/<assessment_id>', teacher_views.get_assessment_data, name='get_assessment_data'),

    path('teacher/class/<int:class_id>', teacher_views.get_class, name='get_teacher_class'),

]
