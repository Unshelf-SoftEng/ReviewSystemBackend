from functools import wraps
from rest_framework.response import Response
from rest_framework import status
from django.core.exceptions import ObjectDoesNotExist
from api.utils.supabase_client import get_supabase_client
from api.models import User

def student_required(view_func):
    @wraps(view_func)
    def wrapped_view(request, *args, **kwargs):

        token = request.headers.get('Authorization')

        if not token:
            return None
        token = token.split("Bearer ")[-1]
        supabase_uid = get_supabase_client().auth.get_user(jwt=token)

        if not supabase_uid:
            return Response({'error': 'User not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)

        try:
            user = User.objects.get(supabase_user_id=supabase_uid)
        except ObjectDoesNotExist:
            return Response({'error': 'User does not exist.'}, status=status.HTTP_404_NOT_FOUND)

        if user.role != 'student':
            return Response({"error": "You are not authorized to access this link"}, status=status.HTTP_403_FORBIDDEN)

        request.user = user
        return view_func(request, *args, **kwargs)

    return wrapped_view
