from django.db import models

# users/models.py
from django.db import models


class User(models.Model):
    supabase_user_id = models.CharField(max_length=255, unique=True)
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=255, null=True)
    last_name = models.CharField(max_length=255, null=True)
    role = models.CharField(max_length=255, null=True)

    def __str__(self):
        return self.email
