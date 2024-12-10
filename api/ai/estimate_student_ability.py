from api.models import AssessmentResult, Answer, Question
from scipy.optimize import minimize
import math


def three_pl_probability(theta, difficulty, discrimination, guessing):
    """Calculate the probability of answering correctly using the 3PL model."""
    exp_term = math.exp(-discrimination * (theta - difficulty))
    return guessing + (1 - guessing) / (1 + exp_term)


def log_likelihood(theta, answers):
    """Compute the negative log-likelihood for a student's answers."""
    likelihood = 0.0

    for answer in answers:
        # Retrieve item parameters: difficulty, discrimination, guessing
        difficulty = answer.question.difficulty
        discrimination = answer.question.discrimination
        guessing = answer.question.guessing

        prob_correct = three_pl_probability(theta, difficulty, discrimination, guessing)

        # Avoid log(0) by bounding probabilities
        prob_correct = max(min(prob_correct, 0.9999), 0.0001)

        # Log-likelihood: Use 1 for correct, 0 for incorrect
        if answer.is_correct:
            likelihood += math.log(prob_correct)
        else:
            likelihood += math.log(1 - prob_correct)

    return -likelihood  # Negative for minimization


def estimate_student_ability_per_category(exam_result_id):
    """Estimate student ability (theta) per category using the 3PL model and MLE."""
    # Retrieve the AssessmentResult and associated answers
    exam_result = AssessmentResult.objects.get(id=exam_result_id)
    answers = Answer.objects.filter(exam_result=exam_result)

    if not answers.exists():
        raise ValueError("No answers found for this exam result.")

    # Group answers by category
    categories = {}
    for answer in answers:
        category = answer.question.category  # Assume a 'category' field exists in Question
        if category not in categories:
            categories[category] = []
        categories[category].append(answer)

    # Function to optimize theta per category
    def estimate_theta_for_answers(answers):
        initial_theta = 0.0
        result = minimize(
            log_likelihood,
            x0=initial_theta,
            args=(answers,),
            method='BFGS'
        )
        return result.x[0] if result.success else None

    # Estimate ability for each category
    category_abilities = {}
    for category, category_answers in categories.items():
        estimated_theta = estimate_theta_for_answers(category_answers)
        category_abilities[category] = round(estimated_theta, 4) if estimated_theta is not None else None

    # Return results
    return {
        "user": exam_result.assessment.user.email,
        "abilities_per_category": category_abilities,
    }
