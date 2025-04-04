from django.urls import path, include


api_urls = [
    path('', include('api.urls.general_urls')),
    path('student/', include('api.urls.student_urls')),
    path('teacher/', include('api.urls.teacher_urls')),
]

urlpatterns = [
    path("api/", include(api_urls)),
]
