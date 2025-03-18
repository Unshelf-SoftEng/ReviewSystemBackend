from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from ..utils.supabase_client import get_supabase_client
from ..models import User, Lesson, Chapter, LessonProgress
from django.shortcuts import get_object_or_404


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


@api_view(['POST'])
def logout_user(request):
    """Logs out the user by revoking their session token."""
    token = request.headers.get('Authorization')

    if not token:
        return Response({'error': 'Authorization token required'}, status=status.HTTP_401_UNAUTHORIZED)

    token = token.split("Bearer ")[-1]
    supabase = get_supabase_client()

    try:
        supabase.auth.sign_out()
        return Response({'message': 'Logout successful'}, status=status.HTTP_200_OK)
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


@api_view(['POST'])
def update_password(request):
    supabase_uid = get_user_id_from_token(request)

    if not supabase_uid:
        return Response({'error': 'User not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)

    try:
        user = User.objects.get(supabase_user_id=supabase_uid)
    except User.DoesNotExist:
        return Response({'error': 'User does not exist.'}, status=status.HTTP_404_NOT_FOUND)

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
def get_user_details(request):
    supabase_uid = get_user_id_from_token(request)

    if not supabase_uid:
        return Response({'error': 'User not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)

    try:
        user = User.objects.get(supabase_user_id=supabase_uid)
    except User.DoesNotExist:
        return Response({'error': 'User does not exist.'}, status=status.HTTP_404_NOT_FOUND)

    user_data = {
        'first_name': user.first_name,
        'last_name': user.last_name,
        'email': user.email,
        'role': user.role,
    }

    return Response(user_data, status=status.HTTP_200_OK)


@api_view(['GET'])
def get_lessons_overall(request):
    user_id = get_user_id_from_token(request)

    if not user_id:
        return Response({'error': 'User not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)

    lessons = Lesson.objects.all().values('id', 'lesson_name')

    return Response(lessons, status=status.HTTP_200_OK)


@api_view(['GET'])
def get_lesson(request, lesson_id):
    user_id = get_user_id_from_token(request)

    if not user_id:
        return Response({'error': 'User not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)

    user = get_object_or_404(User, supabase_user_id=user_id)
    lesson = get_object_or_404(Lesson, id=lesson_id)
    chapters = lesson.chapters.all().order_by("chapter_number")

    lesson_data = {
        "id": lesson.id,
        "lesson_name": lesson.lesson_name,
        "chapters": [
            {
                "id": chapter.id,
                "chapter_name": chapter.chapter_name,
                "chapter_number": chapter.chapter_number,
                "content": chapter.content
            }
            for chapter in chapters
        ]
    }

    # If the user is a student, add their lesson progress
    if user.role == "student":
        lesson_progress, created = LessonProgress.objects.get_or_create(
            user=user,
            lesson=lesson,
            defaults={"progress_percentage": 0.0}  # Default progress if new
        )

        lesson_data["progress"] = {
            "current_chapter": lesson_progress.current_chapter.id if lesson_progress.current_chapter else None,
            "progress_percentage": lesson_progress.progress_percentage
        }

    return Response(lesson_data, status=status.HTTP_200_OK)


@api_view(['POST'])
def update_lesson_progress(request, lesson_id):
    user_id = get_user_id_from_token(request)

    if not user_id:
        return Response({'error': 'User not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)

    user = get_object_or_404(User, supabase_user_id=user_id)

    if user.role != "student":
        return Response({'error': 'Only students can update progress.'}, status=status.HTTP_403_FORBIDDEN)

    lesson = get_object_or_404(Lesson, id=lesson_id)
    data = request.data
    chapter_id = data.get("chapter_id")

    if not chapter_id:
        return Response({'error': 'chapter_id is required.'}, status=status.HTTP_400_BAD_REQUEST)

    chapter = get_object_or_404(Chapter, id=chapter_id, lesson=lesson)

    # Get or create lesson progress
    lesson_progress, created = LessonProgress.objects.get_or_create(
        user=user,
        lesson=lesson,
        defaults={"progress_percentage": 0.0}
    )

    # Update progress
    lesson_progress.current_chapter = chapter

    # Calculate progress percentage
    total_chapters = lesson.chapters.count()
    progress_percentage = (chapter.chapter_number / total_chapters) * 100
    lesson_progress.progress_percentage = progress_percentage

    lesson_progress.save()

    return Response({
        "message": "Lesson progress updated successfully.",
        "progress": {
            "current_chapter": lesson_progress.current_chapter.id,
            "progress_percentage": lesson_progress.progress_percentage
        }
    }, status=status.HTTP_200_OK)
