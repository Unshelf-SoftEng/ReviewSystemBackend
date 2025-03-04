from django.urls import path
from .views import *

urlpatterns = [

    # General Views
    path('register/', register_user, name='register_user'),
    path('login/', login_user, name='login_user'),

    # path('logout/', views.logout_user, name='logout_user'),

    path('refresh-token/', refresh_token, name='refresh_token'),


    # Student Views
    path('student/exam/take', take_exam, name='take_exam'),

    path('student/exam/<exam_id>/submit', submit_exam, name='submit_answers'),

    path('student/exam/<exam_id>', get_exam_results, name='get_exam_results'),

    path('student/quiz/take', take_quiz, name='take_quiz'),

    path('student/abilities', get_student_abilities, name='get_student_abilities'),


    # Teacher Views

    path('teacher/class', get_classes, name='get_classes'),

    path('teacher/class/<class_id>', get_class, name='get_class'),

    path('teacher/class/create', create_class, name='create_class'),

    path('student/class/join', join_class, name='join_class'),

]