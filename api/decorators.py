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
    - If roles are specified, the user must be of the allowed roles.
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapped_view(request, *args, **kwargs):
            supabase_client = get_supabase_client()

            token = request.COOKIES.get('jwt_token')
            refresh_token = request.COOKIES.get('refresh_token')

            if not token:
                return Response({'error': 'Authorization token missing.'}, status=status.HTTP_401_UNAUTHORIZED)

            try:
                user_data = supabase_client.auth.get_user(jwt=token)
            except Exception as e:
                if refresh_token:

                    print('Refreshing the token')

                    try:

                        new_session = supabase_client.auth.refresh_session(refresh_token=refresh_token)

                        if not new_session or not new_session.session:
                            raise Exception("Failed to refresh session")

                        print('Session refreshed')
                        print('new_access_token', new_session.session.access_token)
                        print('new_refresh_token', new_session.session.refresh_token)
                        new_access_token = new_session.session.access_token
                        new_refresh_token = new_session.session.refresh_token

                        user_data = supabase_client.auth.get_user(jwt=new_access_token)
                        user = User.objects.get(supabase_user_id=user_data.user.id)
                        request.user = user
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

                    except Exception as e:
                        return Response({'error': f'{str(e)}'},
                                        status=status.HTTP_404_NOT_FOUND)
                else:
                    print(f"There is no refresh token found")
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
