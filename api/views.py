import json
from rest_framework import status
from rest_framework.decorators import api_view
from django.views.decorators.csrf import csrf_exempt
from rest_framework.response import Response
from .utils.supabase_client import get_supabase_client
from .models import User

# Disable CSRF protection for this view (use cautiously)
@csrf_exempt
@api_view(['POST'])
def register_user(request):
    if request.method == 'POST':
        # Parse data from the request
        data = request.data  # Automatically parses JSON into a dictionary
        email = data.get('email')
        password = data.get('password')
        first_name = data.get('first_name')
        last_name = data.get('last_name')
        role = data.get('role')

        supabase = get_supabase_client()

        # Register the user with Supabase Auth
        try:
            # Supabase registration call
            auth_response = supabase.auth.sign_up({
                'email': email,
                'password': password,
                'options': {
                    'email_redirect_to': 'https://localhost:3000/login/',
                }
            })

            # Store user in the local database (PostgresSQL)
            new_user = User(
                supabase_user_id=auth_response.user.id,
                email=email,
                first_name=first_name,
                last_name=last_name,
                role=role,
            )
            new_user.save()

            # Return success response
            return Response({'message': 'User registered successfully!'}, status=status.HTTP_201_CREATED)
        except Exception as e:

            if "already exists" in str(e).lower():
                return Response({'error': 'Email already registered'}, status=status.HTTP_400_BAD_REQUEST)
            return Response({'error': f'Error: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

# Login view (still incomplete, but here is the structure)
@api_view(['POST'])
@csrf_exempt
def login_user(request):
    if request.method == 'POST':
        # Parse data from the request
        data = request.data  # Automatically parses JSON into a dictionary
        email = data.get('email')
        password = data.get('password')

        supabase = get_supabase_client()

        try:
            # Authenticate user with Supabase
            auth_response = supabase.auth.sign_in_with_password({
                'email': email,
                'password': password
            })

            user = User.objects.get(supabase_user_id=auth_response.user.id)
            role = user.role

            # Return success response with role information
            return Response({
                'message': 'Login successful',
                'jwt_token': auth_response.session.access_token,
                'role': role
            }, status=status.HTTP_200_OK)

        except Exception as e:

            if "invalid login credentials" in str(e).lower():
                return Response({'error': 'Email or Password is incorrect'}, status=status.HTTP_400_BAD_REQUEST)

            return Response({'error': f'Error: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

# def reset_password(request):
#     data = request.data  # Automatically parses JSON into a dictionary
#     email = data.get('email')
#     get_supabase_client().reset_password_email(
#         email=email,
#         options={'redirect_to': 'https://localhost:3000/update_password/'}
#     )
#
# def update_password(request):
#     data = request.data
#
#     password = data.get('password')
#     get_supabase_client().update_user({'password': password})