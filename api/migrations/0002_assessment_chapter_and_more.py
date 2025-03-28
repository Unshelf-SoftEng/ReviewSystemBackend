# Generated by Django 5.1.4 on 2025-03-24 19:39

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="assessment",
            name="chapter",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="api.chapter",
            ),
        ),
        migrations.AlterField(
            model_name="lessonprogress",
            name="current_chapter",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="progress",
                to="api.chapter",
            ),
        ),
        migrations.AlterField(
            model_name="lessonprogress",
            name="current_section",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="progress",
                to="api.section",
            ),
        ),
        migrations.AlterField(
            model_name="section",
            name="chapter",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="sections",
                to="api.chapter",
            ),
        ),
    ]
