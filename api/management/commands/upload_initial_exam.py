from django.core.management.base import BaseCommand
from api.models import User, Question, Assessment

class Command(BaseCommand):
    help = "Creates an initial exam with predefined questions."

    def handle(self, *args, **kwargs):
        user = User.objects.filter(pk=1).first()
        if not user:
            self.stdout.write(self.style.ERROR("User with pk=1 not found."))
            return

        question_ids = [
            '24-A-1', '24-A-2', '24-A-3', '24-A-4', '24-A-5',
            '24-A-6', '24-A-7', '24-A-8', '24-A-9', '24-A-10',
            '24-A-11', '24-A-12', '24-A-13', '24-A-14', '24-A-15',
            '24-A-16', '24-A-17', '24-A-18', '24-A-19', '24-A-20',
            '24-A-21', '24-A-22', '24-A-23', '24-A-24', '24-A-25',
            '24-A-26', '24-A-27', '24-A-28', '24-A-29', '24-A-30',
            '24-A-31', '24-A-32', '24-A-33', '24-A-34', '24-A-35',
            '24-A-36', '24-A-37', '24-A-38', '24-A-39', '24-A-40',
            '24-A-41', '24-A-42', '24-A-43', '24-A-44', '24-A-45',
            '24-A-46', '24-A-47', '24-A-48', '24-A-49', '24-A-50',
            '24-A-51', '24-A-52', '24-A-53', '24-A-54', '24-A-55',
            '24-A-56', '24-A-57', '24-A-58', '24-A-59', '24-A-60',
        ]

        exam, created = Assessment.objects.get_or_create(
            id=1,
            user=user,
            type='exam',
            name='Initial Assessment',
            defaults={
                'status': 'created',
                'question_source': 'previous_exam',
                'source': 'admin_generated',
                'time_in_seconds': 8100,

            }
        )

        if created:
            questions = Question.objects.filter(pk__in=question_ids)
            exam.questions.add(*questions)
            self.stdout.write(self.style.SUCCESS("Exam created successfully."))
        else:
            self.stdout.write(self.style.WARNING("Exam already exists."))