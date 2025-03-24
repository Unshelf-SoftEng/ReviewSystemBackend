from django.urls import include, path

urlpatterns = [
    path('', include('api.urls.general_urls')),
    path('student/', include('api.urls.student_urls')),
    path('teacher/', include('api.urls.teacher_urls')),
]