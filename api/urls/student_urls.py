from django.urls import path
from api.views import student_views

urlpatterns = [
    path('class', student_views.get_class, name='get_student_class'),
    path('class/join', student_views.join_class, name='join_class'),
    path('initial-exam', student_views.get_initial_exam, name='get_initial_exam'),
    path('take-initial-exam', student_views.take_initial_exam, name='take_initial_exam'),
    path('initial-exam-taken', student_views.initial_exam_taken, name='initial_exam_taken'),
    path('assessment/<int:assessment_id>/time-limit', student_views.check_time_limit, name='check_time_limit'),
    path('exam/take', student_views.take_exam, name='take_exam'),
    path('exam/<int:assessment_id>/submit', student_views.submit_assessment, name='submit_exam'),
    path('exam/<int:assessment_id>', student_views.get_exam_results, name='get_exam_results'),
    path('ability', student_views.get_ability, name='get_student_abilities'),
    path('history', student_views.get_history, name='get_student_history'),
    path('quiz/take', student_views.create_student_quiz, name='take_quiz'),
    path('quiz/<int:assessment_id>/submit', student_views.submit_assessment, name='submit_quiz'),
    path('quiz/<int:assessment_id>', student_views.get_exam_results, name='get_quiz_results'),
    path('class/assessments', student_views.get_class_assessments, name='get_class_quizzes'),
    path('take-lesson-quiz', student_views.take_lesson_quiz, name='take_lesson_quiz'),
    path('lessons', student_views.get_lessons, name='get_lessons'),
    path('lessons/<int:lesson_id>', student_views.get_lesson, name='get_lesson'),
]