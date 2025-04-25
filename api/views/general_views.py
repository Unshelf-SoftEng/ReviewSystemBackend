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
from django.shortcuts import render, redirect
from django.contrib import messages
from api.forms import PasswordUpdateForm


def load_accepted_emails():
    """Loads accepted emails from a text file."""
    accepted_emails_path = settings.BASE_DIR / "accepted_emails.txt"
    try:
        with open(accepted_emails_path, "r") as f:
            return set(email.strip().lower() for email in f.readlines())
    except FileNotFoundError:
        print("Did not find accepted emails file.")
        return set()


ACCEPTED_EMAILS = load_accepted_emails()


def is_accepted_email(email):
    """Check if email is either @cit.edu or an accepted email with optional aliasing."""
    email = email.lower().strip()

    # Check for @cit.edu first
    if email.endswith("@cit.edu"):
        return True

    # Check if it's one of your accepted emails (with or without aliases)
    if '@' not in email:
        return False

    local_part, domain = email.split('@', 1)  # Only split on first @
    base_email = f"{local_part.split('+')[0]}@{domain}"

    return base_email in ACCEPTED_EMAILS


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
    email = data.get('email', '').lower().strip()

    if not is_accepted_email(email):  # Add this new function (shown below)
        return Response({'error': 'Only @cit.edu emails or pre-approved emails are allowed'},
                        status=status.HTTP_400_BAD_REQUEST)

    if not is_accepted_email(email):  # Add this new function (shown below)
        return Response({'error': 'Only @cit.edu emails or pre-approved emails are allowed'},
                        status=status.HTTP_400_BAD_REQUEST)

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
                UserAbility(user=new_user, category=category)
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


def update_password(request):
    if request.method == 'POST':
        form = PasswordUpdateForm(request.POST)
        if form.is_valid():
            new_password = form.cleaned_data['new_password']
            confirm_password = form.cleaned_data['confirm_password']
            access_token = request.GET.get('access_token')  # Get the access token from the URL

            # Check if passwords match
            if new_password != confirm_password:
                messages.error(request, "Passwords do not match.")
            else:
                # Use the access token to authenticate and update the user's password
                supabase = get_supabase_client()

                try:
                    user = supabase.auth.api.get_user(access_token)
                    if not user:
                        messages.error(request, 'Invalid access token.')
                    else:
                        # Update the user's password
                        supabase.auth.update_user({'password': new_password})
                        messages.success(request, 'Your password has been updated successfully.')
                        return redirect('login')  # Redirect to the login page after updating the password
                except Exception as e:
                    messages.error(request, f"Error: {str(e)}")

        else:
            messages.error(request, 'Please ensure the form is valid.')

    else:
        form = PasswordUpdateForm()

    return render(request, 'password_update_form.html', {'form': form})


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
def reset_password(request):
    data = request.data
    email = data.get('email')
    supabase = get_supabase_client()

    supabase.auth.reset_password_for_email(
        email,
        {
            "redirect_to": "https://nits-adaptive-nine.vercel.app/update-password",
        }
    )

    return Response({'message': 'Reset email was sent successfully'}, status=status.HTTP_200_OK)


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
