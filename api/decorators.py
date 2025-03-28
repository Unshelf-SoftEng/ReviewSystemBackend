from functools import wraps
from rest_framework.response import Response
from rest_framework import status
from api.utils.supabase_client import get_supabase_client
from api.models import User
from django.shortcuts import get_object_or_404
from gotrue.errors import AuthApiError


def auth_required(*allowed_roles):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped_view(request, *args, **kwargs):
            supabase_client = get_supabase_client()
            token = request.COOKIES.get('jwt_token')
            refresh_token = request.COOKIES.get('refresh_token')

            # If no tokens at all
            if not token and not refresh_token:
                return Response({'error': 'Authentication required'},
                                status=status.HTTP_401_UNAUTHORIZED)

            try:
                if token:
                    print("JWT Token", token)
                    try:
                        user_data = supabase_client.auth.get_user(jwt=token)
                        if user_data and user_data.user:
                            supabase_uid = user_data.user.id
                            user = get_object_or_404(User, supabase_user_id=supabase_uid)

                            if allowed_roles and user.role not in allowed_roles:
                                return Response({"error": "Unauthorized"},
                                                status=status.HTTP_403_FORBIDDEN)

                            request.user = user
                            return view_func(request, *args, **kwargs)
                    except AuthApiError as e:
                        # Token might be expired, try to refresh
                        if not refresh_token:
                            raise

                print("JWT Token is not available")

                # If we get here, we need to refresh the session
                if refresh_token:

                    print("Refresh token", refresh_token)

                    try:
                        new_session = supabase_client.auth.refresh_session(refresh_token=refresh_token)

                        if not new_session or not new_session.session:
                            return Response({'error': 'Session refresh failed'},
                                            status=status.HTTP_401_UNAUTHORIZED)

                        print('Successfully refreshed session')
                        new_access_token = new_session.session.access_token
                        new_refresh_token = new_session.session.refresh_token

                        user_data = supabase_client.auth.get_user(jwt=new_access_token)
                        user = User.objects.get(supabase_user_id=user_data.user.id)

                        if allowed_roles and user.role not in allowed_roles:
                            return Response({"error": "Unauthorized"},
                                            status=status.HTTP_403_FORBIDDEN)

                        request.user = user
                        response = view_func(request, *args, **kwargs)

                        # Set new tokens in cookies
                        response.set_cookie(
                            key='jwt_token',
                            value=new_access_token,
                            httponly=True,
                            secure=True,
                            samesite='None',
                            max_age=30
                        )
                        response.set_cookie(
                            key='refresh_token',
                            value=new_refresh_token,
                            httponly=True,
                            secure=True,
                            samesite='None',
                            max_age=2592000,  # 30 days
                        )
                        return response
                    except AuthApiError as e:
                        print(f"AuthApiError: {str(e)}")
                        return Response({'error': 'Invalid refresh token'},
                                        status=status.HTTP_401_UNAUTHORIZED)

                return Response({'error': 'Authentication required'},
                                status=status.HTTP_401_UNAUTHORIZED)

            except Exception as e:
                return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return wrapped_view

    return decorator
