# Generated by Django 5.1.4 on 2025-04-05 05:51

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0016_assessmentresult_question_order"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="assessmentresult",
            unique_together=set(),
        ),
    ]
