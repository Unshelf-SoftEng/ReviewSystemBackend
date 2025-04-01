from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from api.utils.supabase_client import get_supabase_client
from api.models import User, Category, UserAbility
from api.decorators import auth_required
from django.db import transaction
from django.utils.timezone import now
from datetime import timedelta
from django.conf import settings
import time


def load_accepted_emails():
    """Loads accepted emails from a text file."""
    accepted_emails_path = settings.BASE_DIR / "accepted_emails.txt"
    try:
        with open(accepted_emails_path, "r") as f:
            return set(email.strip().lower() for email in f.readlines())
    except FileNotFoundError:
        print("Did not found accepted emails file.")
        return set()


ACCEPTED_EMAILS = load_accepted_emails()


def normalize_email(email):
    """Normalizes @cit.edu emails by removing + aliases."""
    email = email.lower().strip()
    local_part, domain = email.split("@")
    local_part = local_part.split("+")[0]
    email = f"{local_part}@{domain}"

    return email


@api_view(['POST'])
def register_teacher(request):
    data = request.data
    email = data.get('email')
    password = data.get('password')
    first_name = data.get('first_name')
    last_name = data.get('last_name')
    supabase_client = get_supabase_client()

    if User.objects.filter(email=email).exists():
        return Response({'error': 'Email is already registered'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        auth_response = supabase_client.auth.sign_up({
            'email': email,
            'password': password,
            'options': {
                'email_redirect_to': 'https://nits-adaptive-nine.vercel.app/login',
            }
        })

        supabase_user = getattr(auth_response, 'user', None)
        if not supabase_user or not supabase_user.id:
            return Response({'error': 'User registration failed on Supabase'}, status=status.HTTP_400_BAD_REQUEST)

        # Step 4: Save the user in Django within a transaction
        with transaction.atomic():
            new_user = User.objects.create(
                supabase_user_id=supabase_user.id,
                email=email,
                first_name=first_name,
                last_name=last_name,
                role='teacher',
                verification_sent_at=now(),
            )

        return Response({'message': 'User registered successfully!'}, status=status.HTTP_201_CREATED)

    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
def register_user(request):
    data = request.data
    original_email = data.get('email')
    email = normalize_email(original_email)

    if not email.endswith("@cit.edu") and email not in ACCEPTED_EMAILS:
        return Response({'error': 'Only @cit.edu emails are allowed'},
                        status=status.HTTP_400_BAD_REQUEST)

    if email in ACCEPTED_EMAILS:
        email = original_email

    password = data.get('password')
    first_name = data.get('first_name')
    last_name = data.get('last_name')
    supabase_client = get_supabase_client()

    if User.objects.filter(email=email).exists():
        return Response({'error': 'Email is already registered'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        auth_response = supabase_client.auth.sign_up({
            'email': email,
            'password': password,
            'options': {
                'email_redirect_to': 'https://nits-adaptive-nine.vercel.app/login',
            }
        })

        supabase_user = getattr(auth_response, 'user', None)
        if not supabase_user or not supabase_user.id:
            return Response({'error': 'User registration failed on Supabase'}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            new_user = User.objects.create(
                supabase_user_id=supabase_user.id,
                email=email,
                first_name=first_name,
                last_name=last_name,
                role='student',
                verification_sent_at=now(),
            )
            categories = Category.objects.all()
            user_abilities = [
                UserAbility(user=new_user, category=category, elo_ability=1000, irt_ability=0)
                for category in categories
            ]
            UserAbility.objects.bulk_create(user_abilities)

        return Response({'message': 'User registered successfully!'}, status=status.HTTP_201_CREATED)

    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
def login_user(request):
    data = request.data
    email = data.get('email')
    password = data.get('password')
    supabase = get_supabase_client()
    user = User.objects.filter(email=email).first()

    if not user:
        return Response({'error': 'User not found'}, status=status.HTTP_400_BAD_REQUEST)

    try:

        # Attempt login with Supabase
        auth_response = supabase.auth.sign_in_with_password({
            'email': email,
            'password': password
        })

        # If user exists but email is not confirmed, update status
        if not user.email_confirmed:
            user.email_confirmed = True
            user.save()

        # Create response with tokens
        response = Response({
            'message': 'Login successful',
            'role': user.role,
            'first_name': user.first_name,
            'last_name': user.last_name
        }, status=status.HTTP_200_OK)

        response.set_cookie(
            key='access_token',
            value=auth_response.session.access_token,
            httponly=True,
            secure=True,
            samesite='None',
        )

        response.set_cookie(
            key='refresh_token',
            value=auth_response.session.refresh_token,
            httponly=True,
            secure=True,
            samesite='None',
            max_age=2592000,
        )

        return response

    except Exception as e:
        error_message = str(e).lower()

        print(str(e))

        if "invalid login credentials" in error_message:
            return Response({'error': 'Email or Password is incorrect'}, status=status.HTTP_400_BAD_REQUEST)

        if user and not user.email_confirmed:
            try:
                if not user.verification_sent_at or user.verification_sent_at < now() - timedelta(hours=24):
                    supabase.auth.resend(
                        {
                            "type": "signup",
                            "email": email,
                            "options": {
                                "email_redirect_to": "https://nits-adaptive-nine.vercel.app/login",
                            },
                        }
                    )
                    print("Sent a new email")
                    user.verification_sent_at = now()
                    user.save()

                return Response(
                    {'error': 'Please verify your email. A new verification email has been sent.'},
                    status=status.HTTP_403_FORBIDDEN
                )
            except User.DoesNotExist:
                return Response({'error': 'User not found'}, status=status.HTTP_400_BAD_REQUEST)

        return Response({'error': f'Error: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
def logout_user(request):
    response = Response({'message': 'Logout successful'}, status=status.HTTP_200_OK)
    response.delete_cookie('access_token')
    response.delete_cookie('refresh_token')

    return response


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


@api_view(['POST'])
@auth_required()
def reset_password(request):
    data = request.data
    email = data.get('email')
    get_supabase_client().reset_password_email(
        email=email,
        options={'redirect_to': 'https://localhost:3000/update_password/'}
    )


@api_view(['GET'])
def auth_user(request):
    if hasattr(request, 'user') and request.user.is_authenticated:
        try:
            return Response({
                "id": request.user.id,
                "role": request.user.role,
                "first_name": request.user.first_name,
                "last_name": request.user.last_name
            })
        except AttributeError as e:
            print(f"User attribute error: {e}")
            return Response({
                "error": "User data incomplete",
                "details": str(e)
            }, status=500)

    return Response({"error": "Unauthorized"}, status=401)
