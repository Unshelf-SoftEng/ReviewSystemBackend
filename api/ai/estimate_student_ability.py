from api.models import AssessmentResult, Answer, Question, User, Assessment, UserAbility, Category
from scipy.optimize import minimize
import math
import numpy as np


def three_pl_probability(theta, difficulty, discrimination, guessing):
    """Calculate the probability of answering correctly using the 3PL model."""
    exp_term = math.exp(-discrimination * (theta - difficulty))
    return guessing + (1 - guessing) / (1 + exp_term)


def log_likelihood(theta_array, answers):
    theta = theta_array[0]  # Extract scalar value from array
    likelihood = 0.0

    for answer in answers:
        difficulty = answer.question.difficulty
        discrimination = answer.question.discrimination
        guessing = answer.question.guessing

        prob_correct = three_pl_probability(theta, difficulty, discrimination, guessing)

        # Avoid log(0)
        prob_correct = max(min(prob_correct, 0.9999), 0.0001)

        likelihood += math.log(prob_correct) if answer.is_correct else math.log(1 - prob_correct)

    return -likelihood


def estimate_theta_for_answers(answers):
    initial_theta = np.array([0.0])
    bounds = [(-3, 3)]

    result = minimize(
        log_likelihood,
        x0=initial_theta,
        args=(answers,),
        method='L-BFGS-B',
        bounds=bounds
    )
    return result.x[0] if result.success else None


def estimate_student_ability_per_category(user_id):
    """Estimate student ability (theta) per category using the 3PL model and MLE."""

    print(user_id)

    assessments = Assessment.objects.filter(user_id=user_id).order_by("id")
    all_answers = Answer.objects.filter(exam_result__assessment__in=assessments)

    if not all_answers.exists():
        return {"error": "Student has not taken any assessments."}

    # Group answers by category
    categories = {}
    for answer in all_answers:
        category = answer.question.category
        category_key = str(category.name)
        if category_key not in categories:
            categories[category_key] = []
        categories[category_key].append(answer)

    category_abilities = {}
    for category_name, category_answers in categories.items():
        theta = estimate_theta_for_answers(category_answers)
        category_abilities[
            category_name] = theta if theta is not None else 0  # Defaulting to 0 instead of "Unable to estimate"

    # Optimize category lookup
    category_objs = {c.name: c for c in Category.objects.filter(name__in=category_abilities.keys())}

    for category_name, ability_level in category_abilities.items():
        category_obj = category_objs.get(category_name)

        if category_obj:
            user_ability, created = UserAbility.objects.get_or_create(
                category=category_obj, user_id=user_id,
                defaults={"ability_level": ability_level}  # Use the correct field name
            )
            if not created:  # If the record exists, update it
                user_ability.ability_level = ability_level
                user_ability.save()
