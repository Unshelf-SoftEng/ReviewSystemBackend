from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from api.utils.supabase_client import get_supabase_client
from api.models import User, Lesson, Category, UserAbility
from api.decorators import auth_required


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

        supabase_client = get_supabase_client()

        try:

            auth_response = supabase_client.auth.sign_up({
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

            if role == 'student':
                categories = Category.objects.all()
                for category in categories:
                    UserAbility.objects.create(user=new_user, category=category, elo_ability=1000, irt_ability=0)

                lessons = Lesson.objects.all()

            return Response({'message': 'User registered successfully!'}, status=status.HTTP_201_CREATED)
        except Exception as e:

            if "already exists" in str(e).lower():
                return Response({'error': 'Email already registered'}, status=status.HTTP_400_BAD_REQUEST)
            return Response({'error': f'Error: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
def login_user(request):
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
        first_name = user.first_name
        last_name = user.last_name

        print("Access Token:", auth_response.session.access_token)
        print("Refresh Token:", auth_response.session.refresh_token)

        # Create response
        response = Response({
            'message': 'Login successful',
            'role': role,
            'first_name': first_name,
            'last_name': last_name
        }, status=status.HTTP_200_OK)

        # Set cookies for authentication (HttpOnly for security)
        response.set_cookie(
            key='jwt_token',
            value=auth_response.session.access_token,
            httponly=True,  # Prevent JavaScript access
            secure=True,
            samesite='None'
        )

        response.set_cookie(
            key='refresh_token',
            value=auth_response.session.refresh_token,
            httponly=True,
            secure=True,
            samesite='None'
        )

        return response

    except Exception as e:
        if "invalid login credentials" in str(e).lower():
            return Response({'error': 'Email or Password is incorrect'}, status=status.HTTP_400_BAD_REQUEST)

        return Response({'error': f'Error: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
def refresh(request):
    refresh_token = request.COOKIES.get('refresh_token')

    if not refresh_token:
        return Response({'error': 'Refresh token missing'}, status=status.HTTP_401_UNAUTHORIZED)

    supabase = get_supabase_client()

    try:
        session_data = supabase.auth.refresh_session(refresh_token=refresh_token)

        print(session_data)

        if not session_data or not session_data.session:
            return Response({'error': 'Invalid or expired refresh token'}, status=status.HTTP_401_UNAUTHORIZED)

        # Extract new tokens
        new_access_token = session_data.session.access_token
        new_refresh_token = session_data.session.refresh_token  # MUST BE UPDATED

        response = Response({'message': 'Token refreshed'}, status=status.HTTP_200_OK)

        # Set new access token
        response.set_cookie(
            key='jwt_token',
            value=new_access_token,
            httponly=True,
            secure=True,
            samesite='None'
        )

        # Set new refresh token
        response.set_cookie(
            key='refresh_token',
            value=new_refresh_token,
            httponly=True,
            secure=True,
            samesite='None'
        )

        return response

    except Exception as e:
        return Response({'error': 'Invalid or expired refresh token'}, status=status.HTTP_401_UNAUTHORIZED)

@api_view(['POST'])
def logout_user(request):
    response = Response({'message': 'Logout successful'}, status=status.HTTP_200_OK)

    # Remove cookies
    response.delete_cookie('jwt_token')
    response.delete_cookie('refresh_token')

    return response

@api_view(['POST'])
@auth_required()
def reset_password(request):
    data = request.data
    email = data.get('email')
    get_supabase_client().reset_password_email(
        email=email,
        options={'redirect_to': 'https://localhost:3000/update_password/'}
    )


@api_view(['POST'])
@auth_required()
def update_password(request):
    user: User = request.user
    data = request.data
    supabase = get_supabase_client()
    current_password = data.get('current_password')
    new_password = data.get('new_password')

    try:
        auth_response = supabase.auth.sign_in_with_password({
            'email': user.email,
            'password': current_password
        })
        supabase.auth.update_user({'password': new_password})
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return_data = {
        'message': 'Password updated successfully',
        'jwt_token': auth_response.session.access_token,
        'refresh_token': auth_response.session.refresh_token,
    }

    return Response(return_data, status=status.HTTP_200_OK)


@api_view(['GET'])
@auth_required()
def get_user_details(request):
    user: User = request.user

    user_data = {
        'first_name': user.first_name,
        'last_name': user.last_name,
        'email': user.email,
        'role': user.role,
    }

    return Response(user_data, status=status.HTTP_200_OK)
