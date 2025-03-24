from functools import wraps
from rest_framework.response import Response
from rest_framework import status
from django.core.exceptions import ObjectDoesNotExist
from api.utils.supabase_client import get_supabase_client
from api.models import User

def auth_required(*allowed_roles):
    """
    Decorator to authenticate users.
    - If no roles are specified, only authentication is required.
    - If roles are specified, the user must have one of the allowed roles.
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapped_view(request, *args, **kwargs):
            supabase_client = get_supabase_client()

            # Retrieve tokens from cookies
            token = request.COOKIES.get('jwt_token')
            refresh_token = request.COOKIES.get('refresh_token')

            if not token:
                return Response({'error': 'Authorization token missing.'}, status=status.HTTP_401_UNAUTHORIZED)

            try:
                user_data = supabase_client.auth.get_user(jwt=token)
            except Exception:
                # Token might be expired, try refreshing it
                if refresh_token:
                    try:
                        new_session = supabase_client.auth.refresh_session(refresh_token=refresh_token)
                        if not new_session or not new_session.session:
                            return Response({'error': 'Token refresh failed. Please log in again.'},
                                            status=status.HTTP_401_UNAUTHORIZED)

                        # Extract new access and refresh tokens
                        new_access_token = new_session.session.access_token
                        new_refresh_token = new_session.session.refresh_token

                        # Create response and update cookies
                        response = view_func(request, *args, **kwargs)
                        response.set_cookie(
                            key='jwt_token',
                            value=new_access_token,
                            httponly=True,
                            secure=True,
                            samesite='Lax'
                        )
                        response.set_cookie(
                            key='refresh_token',
                            value=new_refresh_token,
                            httponly=True,
                            secure=True,
                            samesite='Lax'
                        )
                        return response

                    except Exception:
                        return Response({'error': 'Invalid or expired refresh token. Please log in again.'},
                                        status=status.HTTP_401_UNAUTHORIZED)
                else:
                    return Response({'error': 'Invalid or expired token. Please log in again.'},
                                    status=status.HTTP_401_UNAUTHORIZED)

            if not user_data or not user_data.user:
                return Response({'error': 'User not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)

            supabase_uid = user_data.user.id

            try:
                user = User.objects.get(supabase_user_id=supabase_uid)
            except ObjectDoesNotExist:
                return Response({'error': 'User does not exist.'}, status=status.HTTP_404_NOT_FOUND)

            if allowed_roles and user.role not in allowed_roles:
                return Response({"error": "You are not authorized to access this resource"},
                                status=status.HTTP_403_FORBIDDEN)

            request.user = user
            return view_func(request, *args, **kwargs)

        return wrapped_view

    return decorator