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


def estimate_ability_irt(user_id):
    """Estimate student ability (theta) per category using the 3PL model and MLE."""

    user = User.objects.get(pk=user_id)
    all_answers = Answer.objects.filter(assessment_result__user=user)

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
            user_ability = UserAbility.objects.get(category=category_obj, user=user)
            print('Created User Ability')
            user_ability.irt_ability = ability_level
            user_ability.save()


def estimate_ability_elo(user_id):
    """
    Estimate and update student ability using the Elo rating system.
    """
    k = 32  # Learning rate (can be tuned based on system performance)
    user = User.objects.get(pk=user_id)
    assessment_results = AssessmentResult.objects.filter(user=user).order_by('id')

    if not assessment_results.exists():
        return {"error": "Student has not taken any assessments."}

    for result in assessment_results:
        categories = result.assessment.selected_categories

        for category in categories:
            user_ability, created = UserAbility.objects.get_or_create(
                user=user,
                category=category,
                defaults={
                    "elo_ability": 1000,
                    "irt_ability": 0
                }
            )

            # Calculate expected score
            total_difficulty = 0
            for question in result.assessment.selected_questions:
                total_difficulty += question.difficulty

            avg_difficulty = total_difficulty / len(result.assessment.selected_questions)
            expected_score = 1 / (1 + 10 ** ((avg_difficulty - user_ability.ability_level) / 400))

            # Normalize the actual performance (score percentage)
            actual_score = result.score / 100.0

            # Update Elo rating
            new_ability = user_ability.ability_level + k * (actual_score - expected_score)
            user_ability.ability_level = new_ability
            user_ability.save()