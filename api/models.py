from django.db import models
from .utils.util import generate_class_code


class User(models.Model):
    TEACHER = 'teacher'
    STUDENT = 'student'
    ADMIN = 'admin'
    USER_ROLES = [
        (TEACHER, 'Teacher'),
        (STUDENT, 'Student'),
        (ADMIN, 'Admin'),
    ]

    supabase_user_id = models.CharField(max_length=255, unique=True)
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=255, null=True)
    last_name = models.CharField(max_length=255, null=True)
    role = models.CharField(max_length=255, choices=USER_ROLES, default=STUDENT)
    enrolled_class = models.ForeignKey('Class', on_delete=models.SET_NULL, null=True, blank=True)
    email_confirmed = models.BooleanField(default=False)
    verification_sent_at = models.DateTimeField(null=True, blank=True)

    @property
    def full_name(self):
        # Concatenate first_name and last_name with a space in between
        return f"{self.first_name} {self.last_name}"

    def __str__(self):
        return self.full_name


class Category(models.Model):
    name = models.CharField(max_length=255, unique=True)

    def __str__(self):
        return self.name


class Subcategory(models.Model):
    name = models.CharField(max_length=255, unique=True)
    category = models.ForeignKey(Category, related_name='subcategories', on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.category.name} - {self.name}"


class UserAbility(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    irt_ability = models.FloatField()
    elo_ability = models.IntegerField()

    class Meta:
        unique_together = (('user', 'category'),)

    def __str__(self):
        return f"{self.user.full_name} - {self.category.name} - {self.irt_ability}"


class Question(models.Model):
    id = models.CharField(max_length=10, unique=True, primary_key=True)
    question_text = models.TextField()
    image_url = models.TextField(blank=True, null=True)
    category = models.ForeignKey(Category, related_name='questions', on_delete=models.CASCADE)
    subcategory = models.ForeignKey(Subcategory, related_name='questions', on_delete=models.CASCADE, blank=True,
                                    null=True)
    difficulty = models.FloatField(default=0.0)
    discrimination = models.FloatField(default=1.0)
    guessing = models.FloatField(default=0.0)
    choices = models.JSONField()
    correct_answer = models.CharField(max_length=1)

    is_ai_generated = models.BooleanField(default=False)

    def __str__(self):
        return self.question_text


class Assessment(models.Model):
    TYPE_CHOICES = [
        ('exam', 'Exam'),
        ('quiz', 'Quiz')
    ]

    SOURCE_CHOICES = [
        ('student_initiated', 'Student Initiated'),
        ('teacher_generated', 'Teacher Generated'),
        ('lesson_generated', 'Lesson Generated'),
        ('exam_generated', 'Exam Generated'),
        ('admin_generated', 'Admin Generated'),
    ]

    QUESTION_SOURCE_CHOICES = [
        ('previous_exam', 'Previous Exam'),
        ('ai_generated', 'AI Generated'),
        ('mixed', 'Mixed'),
    ]

    name = models.CharField(max_length=50, null=True)
    type = models.CharField(max_length=50, choices=TYPE_CHOICES)
    class_owner = models.ForeignKey('Class', on_delete=models.CASCADE, null=True, blank=True)
    lesson = models.ForeignKey('Lesson', on_delete=models.CASCADE, null=True, blank=True)
    chapter = models.ForeignKey('Chapter', on_delete=models.CASCADE, null=True, blank=True)
    created_by = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, blank=True)
    questions = models.ManyToManyField("Question", related_name="assessments")
    selected_categories = models.ManyToManyField(Category, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    time_limit = models.IntegerField(default=0)
    deadline = models.DateTimeField(null=True, blank=True)
    is_initial = models.BooleanField(default=False)
    source = models.CharField(max_length=50, choices=SOURCE_CHOICES, default='admin_generated')
    question_source = models.CharField(max_length=50, choices=QUESTION_SOURCE_CHOICES, default='previous_exam')
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class AssessmentProgress(models.Model):
    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    start_time = models.DateTimeField(auto_now_add=True)


class AssessmentResult(models.Model):
    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True)
    score = models.IntegerField(default=0)
    start_time = models.DateTimeField(auto_now_add=True)
    time_taken = models.IntegerField(default=0, editable=False)
    last_activity = models.DateTimeField(auto_now=True)
    is_submitted = models.BooleanField(default=False)

    def __str__(self):
        return f'{self.user} scored {self.score} on {self.assessment}'

    def get_time_taken(self):
        return (self.last_activity - self.start_time).seconds


class Answer(models.Model):
    assessment_result = models.ForeignKey(AssessmentResult, related_name='answers', on_delete=models.CASCADE)
    question = models.ForeignKey(Question, related_name='answers', on_delete=models.CASCADE)
    time_spent = models.IntegerField(default=0, editable=False)
    chosen_answer = models.TextField()
    is_correct = models.BooleanField(default=False)

    def __str__(self):
        return f'Answer for {self.question.question_text} by {self.assessment_result.user}'


class Class(models.Model):
    name = models.CharField(max_length=255)
    teacher = models.ForeignKey('User', on_delete=models.CASCADE, limit_choices_to={'role': 'teacher'})
    class_code = models.CharField(max_length=8, unique=True, blank=True, editable=False)

    def save(self, *args, **kwargs):
        if not self.class_code:
            self.class_code = generate_class_code()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Lesson(models.Model):
    name = models.CharField(max_length=255)
    is_locked = models.BooleanField(default=False)

    def __str__(self):
        return self.name


class Chapter(models.Model):
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name='chapters')
    name = models.CharField(max_length=255)
    number = models.PositiveIntegerField()
    is_main_chapter = models.BooleanField(default=False)
    is_locked = models.BooleanField(default=False)

    class Meta:
        ordering = ['number']

    def __str__(self):
        return f"{self.lesson} - Chapter {self.number}. {self.name}"


class Section(models.Model):
    chapter = models.ForeignKey(Chapter, on_delete=models.CASCADE, related_name='sections')
    name = models.CharField(max_length=255)
    number = models.PositiveIntegerField()
    content = models.TextField()

    class Meta:
        ordering = ['number']

    def __str__(self):
        return f"{self.chapter} - Section {self.number}: {self.name}"


class LessonProgress(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='lesson_progress')
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name='progress')
    current_chapter = models.ForeignKey(Chapter, on_delete=models.CASCADE, related_name='progress')
    current_section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name='progress', null=True,
                                        blank=True)

    def __str__(self):
        return f"{self.user.full_name} - {self.lesson.name} | Chapter: {self.current_chapter} | Section: {self.current_section}"
