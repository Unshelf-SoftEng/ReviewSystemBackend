from api.models import AssessmentResult, Answer, Question, User, Assessment, UserAbility, Category
from scipy.optimize import minimize
import math
import numpy as np


def three_pl_probability(theta, difficulty, discrimination, guessing):
    exp_term = math.exp(-discrimination * (theta - difficulty))
    return guessing + (1 - guessing) / (1 + exp_term)


def log_likelihood(theta_array, answers):
    theta = theta_array[0]  # Extract scalar value from array
    likelihood = 0.0

    for answer in answers:
        difficulty = answer.question.ai_difficulty

        if difficulty == 1:
            adjusted_ai_difficulty = -2
        elif difficulty == 2:
            adjusted_ai_difficulty = 0
        else:
            adjusted_ai_difficulty = 2

        discrimination = answer.question.discrimination
        guessing = answer.question.guessing

        prob_correct = three_pl_probability(theta, adjusted_ai_difficulty, discrimination, guessing)

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
    assessment = Assessment.objects.get(class_owner=user.enrolled_class)
    result = AssessmentResult.objects.get(user=user, assessment=assessment)
    all_answers = result.answers.all()

    if not all_answers:
        return {"error": "Student has not taken the initial assessment."}

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
            category_name] = theta if theta is not None else 0

    category_objs = {c.name: c for c in Category.objects.filter(name__in=category_abilities.keys())}

    for category_name, ability_level in category_abilities.items():
        category_obj = category_objs.get(category_name)

        if category_obj:
            user_ability = UserAbility.objects.get(category=category_obj, user=user)
            user_ability.irt_ability = ability_level
            user_ability.save()


def estimate_ability_elo(user_id):
    """
    Estimate and update student ability using the Elo rating system.
    """
    k = 32
    num_choices = 4
    user = User.objects.get(pk=user_id)
    assessment = Assessment.objects.get(class_owner=user.enrolled_class, is_initial=True, is_active=True)

    results = AssessmentResult.objects.filter(user=user, assessment=assessment).order_by('id')

    if not results.exists():
        return

    for result in results:
        categories = result.assessment.selected_categories.all()

        for category in categories:
            user_ability, created = UserAbility.objects.get_or_create(
                user=user,
                category=category,
                defaults={
                    "elo_ability": 1500,
                    "irt_ability": 0
                }
            )

            answers = result.answers.filter(question__category=category)

            for answer in answers:

                difficulty = answer.question.difficulty

                if difficulty == 1:
                    adjusted_difficulty = 1250
                elif difficulty == 2:
                    adjusted_difficulty = 1500
                else:
                    adjusted_difficulty = 1750

                base_probability = 1 / num_choices
                logistic_component = 1 / (1 + math.exp(-(user_ability.elo_ability - adjusted_difficulty)))
                expected_score = base_probability + (1 - base_probability) * logistic_component

                actual_score = 1 if answer.is_correct else 0

                if user_ability.elo_ability is None:
                    user_ability.elo_ability = 1500

                prev_ability = user_ability.elo_ability
                user_ability.elo_ability += round(k * (actual_score - expected_score))
                new_ability = user_ability.elo_ability

                print(f"Category: {category}, Prev Ability: {prev_ability}, New Ability: {new_ability}")

            user_ability.save()


def estimate_ability_elo_time(user_id):
    k = 0.4
    time_scale_factor = 100
    user = User.objects.get(pk=user_id)
    assessment = Assessment.objects.get(class_owner=user.enrolled_class, is_initial=True, is_active=True)
    results = AssessmentResult.objects.filter(user=user, assessment=assessment).order_by('id')

    if not results.exists():
        return

    for result in results:
        categories = result.assessment.selected_categories.all()

        for category in categories:
            user_ability, created = UserAbility.objects.get_or_create(
                user=user,
                category=category,
                defaults={"elo_time_ability": 1500}  # Initialize if missing
            )

            answers = result.answers.filter(question__category=category)

            for answer in answers:
                difficulty = answer.question.ai_difficulty
                adjusted_ai_difficulty = 1250 if difficulty == 1 else 1500 if difficulty == 2 else 1750

                expected_log_time = (adjusted_ai_difficulty - user_ability.elo_time_ability) / time_scale_factor
                actual_time = max(answer.time_spent, 1)  # Avoid log(0)
                actual_log_time = math.log(actual_time) / time_scale_factor
                time_score = (expected_log_time - actual_log_time)  # Now in reasonable range

                expected_correct = 1 / (1 + 10 ** ((adjusted_ai_difficulty - user_ability.elo_time_ability) / 400))
                actual_correct = 1 if answer.is_correct else 0
                correctness_score = (actual_correct - expected_correct)

                combined_update = k * (0.7 * correctness_score + 0.3 * time_score)

                user_ability.elo_time_ability += combined_update

                print(
                    f"Category: {category}, "
                    f"Prev Ability: {user_ability.elo_time_ability - combined_update:.2f}, "
                    f"New Ability: {user_ability.elo_time_ability:.2f}, "
                    f"Time Impact: {time_score:.2f}"
                )

            user_ability.save()
