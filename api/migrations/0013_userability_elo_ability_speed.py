# Generated by Django 5.1.4 on 2025-04-02 23:21

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0012_rename_difficulty_question_irt_difficulty_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="userability",
            name="elo_ability_speed",
            field=models.IntegerField(default=1500),
            preserve_default=False,
        ),
    ]
