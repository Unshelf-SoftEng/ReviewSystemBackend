from django.db import models

# users/models.py
from django.db import models
from .utils.util import generate_class_code


class User(models.Model):
    # User roles
    TEACHER = 'teacher'
    STUDENT = 'student'
    USER_ROLES = [
        (TEACHER, 'Teacher'),
        (STUDENT, 'Student'),
    ]

    supabase_user_id = models.CharField(max_length=255, unique=True)
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=255, null=True)
    last_name = models.CharField(max_length=255, null=True)
    role = models.CharField(max_length=255, choices=USER_ROLES, default=STUDENT)

    @property
    def full_name(self):
        # Concatenate first_name and last_name with a space in between
        return f"{self.first_name} {self.last_name}"

    def __str__(self):
        return self.email


class Category(models.Model):
    name = models.CharField(max_length=255, unique=True)

    def __str__(self):
        return self.name


class Question(models.Model):
    id = models.CharField(max_length=10, unique=True, primary_key=True)
    question_text = models.CharField()
    image_url = models.CharField(max_length=255, null=True)
    category = models.ForeignKey(Category, related_name='questions', on_delete=models.CASCADE)
    difficulty = models.FloatField(default=0.0)
    discrimination = models.FloatField(default=1.0)
    guessing = models.FloatField(default=0.0)
    choices = models.JSONField()
    correct_answer = models.CharField(max_length=255)

    def __str__(self):
        return self.question_text


class Exam(models.Model):
    user = models.ForeignKey('User', on_delete=models.CASCADE)
    questions = models.ManyToManyField("Question", related_name="exams")

    def __str__(self):
        return f"Exam for {self.user.email}"


class ExamResult(models.Model):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE)
    score = models.IntegerField(default=0)
    time_taken = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.exam.user.full_name} - {self.exam} - {self.score}'


class Answer(models.Model):
    exam_result = models.ForeignKey(ExamResult, related_name='answers', on_delete=models.CASCADE)
    question = models.ForeignKey(Question, related_name='question', on_delete=models.CASCADE)
    time_spent = models.IntegerField(default=0)
    chosen_answer = models.CharField(max_length=255)
    is_correct = models.BooleanField(default=False)

    def __str__(self):
        return f'Answer for {self.question.question_text} by {self.exam_result.exam.user_id.email}'


class Class(models.Model):
    name = models.CharField(max_length=255)
    teacher = models.ForeignKey('User', on_delete=models.CASCADE, limit_choices_to={'role': 'teacher'})
    students = models.ManyToManyField('User', related_name='enrolled_classes', limit_choices_to={'role': 'student'})
    class_code = models.CharField(max_length=8, unique=True, blank=True, editable=False)

    def save(self, *args, **kwargs):
        if not self.class_code:
            self.class_code = generate_class_code()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name
