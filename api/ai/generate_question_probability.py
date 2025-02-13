import numpy as np
import random
from collections import deque
from tensorflow.keras import Sequential
from tensorflow.keras.layers import Dense
from tensorflow.keras.optimizers import Adam
from api.models import Question


class DQNAgent:
    """
    A Deep Q-Network (DQN) agent for optimizing quiz question selection.
    """

    def __init__(self, state_size, action_size):
        self.state_size = state_size  # Size of the state vector (e.g., learner's ability in each category)
        self.action_size = action_size  # Number of possible actions (question sets)
        self.memory = deque(maxlen=2000)  # Memory buffer for experience replay
        self.gamma = 0.95  # Discount factor for future rewards
        self.epsilon = 1.0  # Exploration rate
        self.epsilon_min = 0.01  # Minimum exploration rate
        self.epsilon_decay = 0.995  # Decay rate for exploration
        self.learning_rate = 0.001  # Learning rate for the neural network
        self.model = self._build_model()  # Build the DQN model

    def _build_model(self):
        """
        Builds the neural network model for the DQN.
        """
        model = Sequential()
        model.add(Dense(24, input_dim=self.state_size, activation='relu'))
        model.add(Dense(24, activation='relu'))
        model.add(Dense(self.action_size, activation='linear'))
        model.compile(loss='mse', optimizer=Adam(learning_rate=self.learning_rate))
        return model

    def remember(self, state, action, reward, next_state, done):
        """
        Stores experiences in the memory buffer for experience replay.
        """
        self.memory.append((state, action, reward, next_state, done))

    def act(self, state, question_probs):
        """
        Selects a question based on RL and the given question probabilities.

        Args:
            state (numpy array): Learner's ability state.
            question_probs (dict): Dictionary mapping question_id -> probability.

        Returns:
            str: Selected question ID.
        """
        question_ids = np.array(list(question_probs.keys()))
        prob_values = np.array(list(question_probs.values()))

        if np.random.rand() <= self.epsilon:
            # Exploration: Choose a question randomly based on probabilities
            return np.random.choice(question_ids, p=prob_values)

        # Exploitation: Use the RL model to predict the best action
        q_values = self.model.predict(state)  # Get Q-values from the model

        # Apply softmax-like transformation to avoid negative values
        q_values = np.exp(q_values[0])
        q_values /= q_values.sum()

        # Weight by the actual question probabilities
        weighted_q_values = q_values * prob_values
        selected_index = np.argmax(weighted_q_values)

        return question_ids[selected_index]

    def replay(self, batch_size):
        """
        Trains the DQN using experience replay.
        """
        minibatch = random.sample(self.memory, batch_size)
        for state, action, reward, next_state, done in minibatch:
            target = reward
            if not done:
                target = reward + self.gamma * np.amax(self.model.predict(next_state)[0])
            target_f = self.model.predict(state)
            target_f[0][action] = target
            self.model.fit(state, target_f, epochs=1, verbose=0)
        if self.epsilon > self.epsilon_min:
            self.epsilon *= self.epsilon_decay


def generate_question_probability(category, theta_k):
    """
    Generates a probability distribution for questions in a given category based on the learner's ability (theta_k).
    """
    questions = Question.objects.filter(category=category)
    if not questions.exists():
        raise ValueError("No questions available for the specified category.")

    probabilities = {}
    for question in questions:
        b_i = question.difficulty  # Difficulty parameter of the question
        probability = np.exp(-np.abs(b_i - theta_k))  # Probability formula
        probabilities[question.id] = probability

    # Normalize probabilities to sum to 1
    total_probability = sum(probabilities.values())
    for question_id in probabilities:
        probabilities[question_id] /= total_probability

    return probabilities


def update_learner_ability(theta_k, responses):
    """
    Updates the learner's ability estimate (theta_k) based on their quiz responses.
    """
    question_ids = [response[0] for response in responses]
    questions = Question.objects.filter(id__in=question_ids)

    numerator = 0
    denominator = 0
    for response in responses:
        question_id, u_i = response
        question = questions.get(id=question_id)
        a_i = question.discrimination  # Discrimination parameter
        b_i = question.difficulty  # Difficulty parameter
        c_i = question.guessing  # Guessing parameter
        P_i = c_i + (1 - c_i) / (1 + np.exp(-a_i * (theta_k - b_i)))  # 3PL IRT model
        numerator += a_i * (u_i - P_i)
        denominator += a_i ** 2 * P_i * (1 - P_i)

    if denominator != 0:
        theta_k += numerator / denominator
    return theta_k


def generate_quiz_with_rl(categories, theta_k, num_questions=10):
    """
    Generates a quiz using Reinforcement Learning (RL) across multiple categories,
    considering a list of abilities corresponding to each category.

    Args:
        categories (list of str): List of categories.
        theta_k (list of float): Learner's ability levels for each category.
        num_questions (int): Number of questions to select.

    Returns:
        list: Selected question IDs.
    """
    # Initialize the DQN agent (if not already initialized)
    if not hasattr(generate_quiz_with_rl, 'agent'):
        state_size = len(categories)  # Each category has a separate ability
        action_size = 100  # Max number of possible questions
        generate_quiz_with_rl.agent = DQNAgent(state_size, action_size)

    agent = generate_quiz_with_rl.agent

    # Collect all question probabilities across categories
    question_probs = {}
    for category, ability in zip(categories, theta_k):
        category_probs = generate_question_probability(category, ability)
        question_probs.update(category_probs)  # Merge probabilities

    prob_values = np.array(list(question_probs.values()))

    # Normalize probabilities to sum to 1 (to avoid numerical instability)
    prob_values /= prob_values.sum()

    # Convert learner's abilities into a state vector
    state = np.array(theta_k).reshape(1, -1)

    # RL selects the questions
    selected_questions = set()
    while len(selected_questions) < num_questions:
        question_id = agent.act(state, question_probs)  # RL selects an index
        selected_questions.add(question_id)  # Direct selection

    return list(selected_questions)


def update_rl_model(theta_k, selected_question_ids, responses, batch_size=32):
    """
    Updates the RL model based on learner responses.
    """
    agent = generate_quiz_with_rl.agent  # Get the RL agent

    # Calculate reward (e.g., number of correct answers)
    reward = sum(response[1] for response in responses)

    # Update learner's ability estimate
    updated_theta_k = update_learner_ability(theta_k, responses)

    # Store experience in RL memory
    state = np.array([theta_k]).reshape(1, -1)
    next_state = np.array([updated_theta_k]).reshape(1, -1)
    done = False  # Not a terminal state

    agent.remember(state, selected_question_ids, reward, next_state, done)

    # Train the DQN agent
    if len(agent.memory) > batch_size:
        agent.replay(batch_size)

    return updated_theta_k
