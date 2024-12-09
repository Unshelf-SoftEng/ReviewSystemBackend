from django.urls import path
from . import views

urlpatterns = [
    path('register/', views.register_user, name='register_user'),
    path('login/', views.login_user, name='login_user'),

    path('student/exam/take', views.take_exam, name='take_exam'),

    path('student/exam/<exam_id>', views.get_exam, name='get_exam'),

    path('student/exam/<exam_id>/submit', views.submit_answers, name='submit_answers'),

    path('student/exam/<exam_id>/results', views.get_exam_results, name='get_exam_results'),
]