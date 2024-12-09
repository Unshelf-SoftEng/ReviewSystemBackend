from django.urls import path
from . import views

urlpatterns = [
    path('register/', views.register_user, name='register_user'),
    path('login/', views.login_user, name='login_user'),

    # path('logout/', views.logout_user, name='logout_user'),

    path('refresh-token/', views.refresh_token, name='refresh_token'),

    path('student/exam/take', views.take_exam, name='take_exam'),

    path('student/exam/<exam_id>', views.get_exam, name='get_exam'),

    path('student/exam/<exam_id>/submit', views.submit_answers, name='submit_answers'),

    path('student/exam/<exam_id>/results', views.get_exam_results, name='get_exam_results'),

    path('teacher/class', views.get_classes, name='get_classes'),

    path('teacher/class/<class_id>', views.get_class, name='get_class'),

    path('teacher/class/create', views.create_class, name='create_class'),

    path('student/class/join', views.join_class, name='join_class'),
]