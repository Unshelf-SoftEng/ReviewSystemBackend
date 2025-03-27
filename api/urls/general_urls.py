from django.urls import path
from api.views import general_views

urlpatterns = [
    path('register/', general_views.register_user, name='register_user'),
    path('login/', general_views.login_user, name='login_user'),
    path('logout/', general_views.logout_user, name='logout_user'),
    path('auth-user/', general_views.auth_user, name='auth_user'),
    path('profile/', general_views.get_user_details, name='get_user_details'),
    path('update-password/', general_views.update_password, name='update_password'),
]