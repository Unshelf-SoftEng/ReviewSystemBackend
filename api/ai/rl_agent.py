import numpy as np
import random
from collections import deque

from tensorflow.keras import Sequential, Input
from tensorflow.keras.layers import Dense
from tensorflow.keras.optimizers import Adam
from scipy.special import softmax
from api.models import Question  # Import Django model


class DQNAgent:
    """
    A Deep Q-Network (DQN) agent for optimizing quiz question selection.
    """

    def __init__(self, state_size, action_size, ability_estimate=None):
        """
        Initializes the DQN agent with the given ability estimate.

        Args:
        state_size: The size of the state vector (e.g., learner's ability in each category).
        action_size: The number of possible actions (question sets).
        ability_estimate: The learner's initial ability estimate from the IRT model (default: None).
        """
        self.state_size = state_size  # Size of the state vector
        self.action_size = action_size  # Number of possible actions (question sets)
        self.memory = deque(maxlen=2000)  # Memory buffer for experience replay
        self.gamma = 0.95  # Discount factor for future rewards
        self.epsilon = 1.0  # Exploration rate
        self.epsilon_min = 0.01  # Minimum exploration rate
        self.epsilon_decay = 0.995  # Decay rate for exploration
        self.learning_rate = 0.001  # Learning rate for the neural network
        self.model = self._build_model()  # Build the DQN model

        # Initialize the state based on the ability estimate (if provided)
        if ability_estimate is not None:
            self.state = np.array(ability_estimate)  # Set state with ability estimate
        else:
            self.state = np.zeros(self.state_size)  # Default to zero if no ability estimate is given

        # Optionally, store this initial state as the first memory (experience)
        self.remember([], 0, self.state, done=True)

    def _build_model(self):
        """
        Builds the neural network model for the DQN.
        """
        model = Sequential()
        model.add(Input(shape=(self.state_size,)))
        model.add(Dense(24, activation='relu'))
        model.add(Dense(24, activation='relu'))
        model.add(Dense(self.action_size, activation='linear'))
        model.compile(loss='mse', optimizer=Adam(learning_rate=self.learning_rate))
        return model

    def remember(self, action, reward, next_state, done):
        """
        Stores experiences in the memory buffer for experience replay.
        """
        self.memory.append((self.state, action, reward, next_state, done))

    def act(self, question_probs):
        question_ids = np.array(list(question_probs.keys()))
        prob_values = np.array(list(question_probs.values()))

        if prob_values.sum() == 0 or np.isnan(prob_values).any():
            prob_values = np.ones_like(prob_values) / len(prob_values)  # Assign equal probability
        else:
            prob_values /= prob_values.sum()  # Normalize

        if np.random.rand() <= self.epsilon:
            return np.random.choice(question_ids, p=prob_values)  # Exploration

        # Exploitation: Use Q-values from the model
        q_values = self.model.predict(np.array(self.state).reshape(1, -1))

        # Use softmax for numerical stability
        q_values = softmax(q_values[0])

        # Weight by the actual question probabilities
        weighted_q_values = q_values * prob_values
        selected_index = np.argmax(weighted_q_values)

        return question_ids[selected_index]

    def replay(self, batch_size):
        if len(self.memory) < batch_size:
            return

        minibatch = random.sample(self.memory, batch_size)
        for state, action, reward, next_state, done in minibatch:
            target = reward
            if not done:
                target = reward + self.gamma * np.amax(self.model.predict(next_state)[0])
            target_f = self.model.predict(state)
            target_f[0][action] = target
            self.model.fit(state, target_f, epochs=1, verbose=0)

        # Update epsilon (exploration-exploitation balance)
        if self.epsilon > self.epsilon_min:
            self.epsilon *= self.epsilon_decay


def generate_question_probability(category, theta_k):
    filtered_questions = Question.objects.filter(category=category)

    if not filtered_questions:
        raise ValueError("No questions available for the specified category.")

    probabilities = {}

    for question in filtered_questions:
        b_i = question["difficulty"]  # Difficulty parameter of the question
        probability = np.exp(-np.abs(b_i - theta_k))  # Probability formula
        probabilities[question["id"]] = probability

    # Normalize probabilities to sum to 1
    total_probability = sum(probabilities.values())
    for question_id in probabilities:
        probabilities[question_id] /= total_probability

    return probabilities


def generate_quiz_with_rl(rl_agent, categories, theta_k, num_questions=10):
    # Collect all question probabilities across categories
    question_probs = {}
    for category, ability in zip(categories, theta_k):
        category_probs = generate_question_probability(category, ability)
        question_probs.update(category_probs)  # Merge probabilities

    # RL selects the questions
    selected_questions = set()
    while len(selected_questions) < num_questions:
        question_id = rl_agent.act(question_probs)
        selected_questions.add(question_id)

    return list(selected_questions)


def update_learner_ability(responses, theta_k):
    # Create temporary storage for updates per category
    category_updates = {category: {"numerator": 0, "denominator": 0} for category in theta_k}

    for question_id, u_i in responses.items():
        question = Question.objects.filter(id=question_id).first()

        if question is None:
            print(f"Warning: Question ID {question_id} not found. Skipping.")
            continue

        category = question["category"]
        if category not in theta_k:
            print(f"Warning: Category '{category}' not found in theta_k. Skipping.")
            continue

        # Get IRT parameters
        a_i = question.get("discrimination", 1.0)
        b_i = question.get("difficulty", 0.0)
        c_i = question.get("guessing_rate", 0.25)

        # Get learner's ability for the category
        theta_k_value = theta_k[category]

        # 3PL IRT model probability
        P_i = c_i + (1 - c_i) / (1 + np.exp(-a_i * (theta_k_value - b_i)))

        # Update numerators and denominators per category
        category_updates[category]["numerator"] += a_i * (u_i - P_i)
        category_updates[category]["denominator"] += a_i ** 2 * P_i * (1 - P_i)

    # Update theta_k for each category
    for category, update in category_updates.items():
        if update["denominator"] > 0:
            theta_k[category] += update["numerator"] / update["denominator"]
        else:
            print(f"Warning: No valid updates for category '{category}'.")

    return theta_k


def compute_reward(responses, theta_k):
    performance_score = 0
    difficulty_penalty = 0
    total_questions = len(responses)

    for qid, correctness in responses.items():
        # Find the question by id in the global 'questions' list
        question = Question.objects.filter(id=qid).first()

        if question:
            difficulty = question["difficulty"]
            category = question["category"]

            learner_ability = theta_k.get(category, 0)  # Use global learner ability (theta_k)
            ideal_difficulty = learner_ability + 0.1  # Slightly above ability for challenge

            # Add the performance score for correct answers (correctness is 1 or 0)
            performance_score += difficulty * correctness

            # Calculate the difficulty penalty (larger difference between ideal and real difficulty is worse)
            difficulty_penalty += abs(difficulty - ideal_difficulty) * 5  # Penalize mismatch

    if total_questions == 0:
        return 0  # Avoid division by zero

    # Normalize the reward by total questions and subtract the penalty
    reward = performance_score - (difficulty_penalty / total_questions)

    return reward


def update_rl_model(rl_agent, responses, batch_size=32):
    # Calculate reward (e.g., sum of correct answers)
    reward = compute_reward(responses)

    # Update learner's ability estimate
    updated_theta_k = update_learner_ability(responses)

    # Convert theta_k to numpy array for RL state representation
    next_state = np.array([list(updated_theta_k.values())]).reshape(1, -1)
    done = False  # Not a terminal state

    # Store experience in RL memory
    rl_agent.remember(list(responses.keys()), reward, next_state, done)

    # Train the DQN agent if enough memory is available
    if len(rl_agent.memory) > batch_size:
        rl_agent.replay(batch_size)

    rl_agent.state = next_state

    return updated_theta_k
