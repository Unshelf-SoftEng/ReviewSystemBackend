from django.urls import path
from api.views import teacher_views

urlpatterns = [
    path('classes', teacher_views.get_classes, name='get_classes'),
    path('class/create', teacher_views.create_class, name='create_class'),
    path('class/student/<int:student_id>', teacher_views.get_student_data, name='get_student_data'),

    path('class/<int:class_id>/create-assessment', teacher_views.create_assessment, name='create_assessment'),
    path('class/<int:class_id>/view-initial-exam', teacher_views.view_initial_exam, name='get_initial_exam'),
    path('class/<int:class_id>/open-initial-exam', teacher_views.open_initial_exam, name='open_initial_exam'),
    path('class/<int:class_id>/assessments', teacher_views.get_class_assessments, name='get_all_quizzes'),
    path('class/<int:class_id>/lesson/<int:lesson_id>/results', teacher_views.get_lesson_quiz_data,
         name='get_lesson_quiz'),
    path('class/<int:class_id>/chapter/<int:chapter_id>/results', teacher_views.get_chapter_quiz,
         name='get_chapter_quiz'),
    path('class/<int:class_id>/create-initial-exam', teacher_views.create_initial_assessment,
         name='create_initial_assessment'),
    path('class/<int:class_id>/estimate-students-ability', teacher_views.estimate_ability_students,
         name='estimate_ability_students'),
    path('class/<int:class_id>', teacher_views.get_class, name='get_teacher_class'),
    path('get_questions', teacher_views.get_all_questions, name='get_all_questions'),
    path('assessment/<int:assessment_id>/results-students', teacher_views.get_assessment_results_students, name='get_assessment_results_students'),
    path('assessment/<int:assessment_id>/results-questions', teacher_views.get_assessment_results_questions, name='get_assessment_results_questions'),
    path('assessment/<int:assessment_id>/update', teacher_views.update_assessment, name='update_assessment'),
    path('assessment/<int:assessment_id>/delete', teacher_views.delete_assessment, name='delete_assessment'),
    path('assessment/<int:assessment_id>', teacher_views.get_assessment_data, name='get_assessment_data'),

    path('lessons/', teacher_views.get_lessons, name='get_lessons'),
    path('lesson/<int:lesson_id>/chapter/<int:chapter_id>', teacher_views.get_chapter, name='get_lesson'),
    path('lesson/<int:lesson_id>', teacher_views.get_lesson, name='get_lesson'),

    path('class/<int:class_id>/create-final-exam', teacher_views.create_final_assessment,
         name='create_final_assessment'),
]