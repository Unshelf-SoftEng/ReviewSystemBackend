# Generated by Django 5.1.4 on 2025-04-01 01:56

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0006_user_email_confirmed"),
    ]

    operations = [
        migrations.RenameField(
            model_name="assessmentresult",
            old_name="created_at",
            new_name="start_time",
        ),
    ]
