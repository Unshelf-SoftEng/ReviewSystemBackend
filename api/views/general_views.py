from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from ..utils.supabase_client import get_supabase_client
from ..models import User


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
                'refresh_token': auth_response.session.refresh_token,
                'role': role
            }, status=status.HTTP_200_OK)

        except Exception as e:

            if "invalid login credentials" in str(e).lower():
                return Response({'error': 'Email or Password is incorrect'}, status=status.HTTP_400_BAD_REQUEST)

            return Response({'error': f'Error: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
def refresh_token(request):
    # Retrieve the refresh_token from the frontend request

    ref_token = request.data.get('refresh_token')

    if not ref_token:
        return Response({'error': 'Refresh token is required'}, status=status.HTTP_400_BAD_REQUEST)

    # Get the Supabase client
    supabase = get_supabase_client()

    try:
        # Use the Supabase client to refresh the token
        auth_response = supabase.auth.refresh_session(ref_token)

        if auth_response:
            # Extract new access and refresh tokens
            new_access_token = auth_response.session.access_token

            return Response({
                'jwt_token': new_access_token,
                'refresh_token': auth_response.session.refresh_token,
            }, status=status.HTTP_200_OK)
        else:
            return Response({'error': 'Unable to refresh token'}, status=status.HTTP_400_BAD_REQUEST)

    except Exception as e:
        return Response({'error': f'Error: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)


def get_user_id_from_token(request):
    """Helper function to extract the user ID from the Supabase JWT token."""
    token = request.headers.get('Authorization')
    if not token:
        return None
    token = token.split("Bearer ")[-1]

    try:
        response = get_supabase_client().auth.get_user(jwt=token)
        return response.user.id
    except Exception as e:
        print(str(e))
        return None


def reset_password(request):
    data = request.data  # Automatically parses JSON into a dictionary
    email = data.get('email')
    get_supabase_client().reset_password_email(
        email=email,
        options={'redirect_to': 'https://localhost:3000/update_password/'}
    )


def update_password(request):
    data = request.data

    password = data.get('password')
    get_supabase_client().update_user({'password': password})


@api_view(['GET'])
def get_lessons_overall(request):
    user_id = get_user_id_from_token(request)

    if not user_id:
        return Response({'error': 'User not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)

    lesson_titles = {
        "titles": ['Basic Theory', 'Computer System', 'Technology Element', 'Development Technology',
                   'Project Management', 'Service Management', 'Business Strategy', 'System Strategy',
                   'Corporate and Legal Affairs']
    }

    return Response(lesson_titles, status=status.HTTP_200_OK)


@api_view(['GET'])
def get_lesson(request, lesson_id):
    user_id = get_user_id_from_token(request)

    if not user_id:
        return Response({'error': 'User not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)

    current_chapter = {}
    chapters = {}
    data = []

    return Response(chapters, status=status.HTTP_200_OK)