import base64
import pickle
import numpy as np
from collections import deque
from tensorflow.keras import Sequential, Input
from tensorflow.keras.layers import Dense
from tensorflow.keras.optimizers import Adam
from api.models import RLAgentState, Question
import random


class DQNAgent:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(DQNAgent, cls).__new__(cls, *args, **kwargs)
            cls._instance._initialize_agent()
        return cls._instance

    def _initialize_agent(self):
        self.state_size = 4
        self.action_size = 1480
        self.memory = deque(maxlen=2000)
        self.gamma = 0.95
        self.epsilon = 1.0
        self.epsilon_min = 0.01
        self.epsilon_decay = 0.995
        self.learning_rate = 0.001
        self.model = self._build_model()

        self.state = np.zeros(self.state_size)  # Default state
        self.remember([], 0, self.state, done=True)

        self.load_state_from_db()

    def _build_model(self):
        model = Sequential()
        model.add(Input(shape=(self.state_size,)))
        model.add(Dense(24, activation='relu'))
        model.add(Dense(24, activation='relu'))
        model.add(Dense(self.action_size, activation='linear'))
        model.compile(loss='mse', optimizer=Adam(learning_rate=self.learning_rate))
        return model

    def save_state_to_db(self):
        # Serialize the model weights and state
        model_weights = pickle.dumps(self.model.get_weights())
        state = self.state.tolist()  # Convert the state to a list for JSON storage

        # Save to database (only one entry, update it)
        RLAgentState.objects.update_or_create(
            pk=1,  # We are assuming only one record to store the state for the whole system
            defaults={
                'state': state,
                'model_weights': model_weights
            }
        )

    def load_state_from_db(self):
        try:
            agent_state = RLAgentState.objects.get(pk=1)  # We assume only one record
            self.state = np.array(agent_state.state)  # Load state
            model_weights = pickle.loads(agent_state.model_weights)  # Load model weights
            self.model.set_weights(model_weights)  # Set model weights
        except RLAgentState.DoesNotExist:
            pass  # If no state exists, we keep the default state

    def remember(self, action, reward, next_state, done):
        self.memory.append((self.state, action, reward, next_state, done))

    def act(self, questions, ability):
        question_ids = np.array([q["id"] for q in questions])
        difficulties = np.array([q["difficulty"] for q in questions])

        if np.random.rand() <= self.epsilon:
            return np.random.choice(question_ids)

        closeness = -np.abs(difficulties - ability)

        q_values = self.model.predict(np.array(self.state).reshape(1, -1))[0]

        if len(q_values) != len(questions):
            raise ValueError("Mismatch between Q-values and questions passed.")

        combined_scores = q_values + closeness

        selected_index = np.argmax(combined_scores)
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


def decide_questions_for_categories(available_questions_per_category, abilities, remaining_questions):
    """
    Decide how many questions to select from each category based on user ability and remaining questions.
    Focus more on categories with lower ability.
    """
    category_decision = {}
    total_weight = 0
    category_weights = {}

    for category in available_questions_per_category:
        ability = abilities.get(category, 0.0)
        ability_weight = 1 / (ability + 1)
        category_weights[category] = ability_weight
        total_weight += ability_weight

    for category, weight in category_weights.items():
        normalized_weight = weight / total_weight if total_weight > 0 else 0
        num_questions_for_category = int(remaining_questions * normalized_weight)
        available_questions = available_questions_per_category[category]
        num_questions_for_category = min(num_questions_for_category, len(available_questions))
        category_decision[category] = num_questions_for_category

    return category_decision


def generate_quiz_with_rl(rl_agent, abilities, categories, total_questions):
    selected_questions = set()

    available_questions_dict = {}
    for category in categories:
        category_name = category.name
        questions_in_category = Question.objects.filter(category=category)

        # Store actual Question objects, not just IDs
        available_questions = [
            {"id": q.id, "difficulty": q.elo_difficulty, "question": q} for q in questions_in_category
        ]

        available_questions_dict[category_name] = available_questions

    remaining_questions = total_questions

    if len(available_questions_dict) > 1:
        print('Remaining Questions', remaining_questions)
        category_decision = decide_questions_for_categories(
            available_questions_dict, abilities, remaining_questions
        )
        print("Category Decision:", category_decision)
    else:
        category_decision = {category: remaining_questions for category in available_questions_dict}

    for category, num_questions_for_category in category_decision.items():
        ability = abilities.get(category, 0.0)
        available_questions = available_questions_dict.get(category, [])

        if not available_questions:
            print(f"Warning: No questions found for category '{category}'")
            continue

        selected_for_category = 0
        while selected_for_category < num_questions_for_category and remaining_questions > 0:
            question_id = str(rl_agent.act(available_questions, ability))

            question_obj = next((q["question"] for q in available_questions if str(q["question"].id) == question_id),
                                None)

            if question_obj and question_obj not in selected_questions:
                selected_questions.add(question_obj)
                selected_for_category += 1
                remaining_questions -= 1
            else:
                continue

    return list(selected_questions)


def update_learner_ability(responses, abilities, K=32):
    """
    Update the learner's ability using the Elo rating system.

    :param responses: Dictionary where keys are question IDs and values are correctness (1 for correct, 0 for incorrect).
    :param abilities: Dictionary of learner abilities per category.
    :param K: Elo rating constant (default is 32).
    :return: Updated dictionary of learner abilities.
    """
    category_updates = {category: 0 for category in abilities}

    for question_id, u_i in responses.items():
        question = Question.objects.filter(id=question_id).first()

        if question is None:
            print(f"Warning: Question ID {question_id} not found. Skipping.")
            continue

        category = question.category.name
        if category not in abilities.keys():
            print(f"Warning: Category '{category}' not found in theta_k. Skipping.")
            continue

        # Get difficulty of the question
        difficulty = question.get("difficulty", 0.0)

        # Get learner's current ability for the category
        learner_ability = abilities[category]

        # Expected score based on the Elo rating formula
        expected_score = 1 / (1 + 10 ** ((difficulty - learner_ability) / 400))

        # Update the learner's ability using the Elo rating system
        # S is the actual score: 1 for correct answer, 0 for incorrect answer
        S = u_i

        # Apply the Elo rating formula to update the ability
        category_updates[category] += K * (S - expected_score)

    # Update the learner's ability for each category
    for category, update in category_updates.items():
        if update != 0:
            abilities[category] += update

    return abilities


def compute_reward(responses, abilities, k_factor=16):
    total_reward = 0

    for qid, correctness in responses.items():
        question = Question.objects.filter(id=qid).first()

        if question:
            difficulty = question.difficulty
            category = question.category

            learner_rating = abilities.get(category, 1500)

            expected = 1 / (1 + 10 ** ((difficulty - learner_rating) / 400))

            actual = correctness

            reward = k_factor * (actual - expected)

            total_reward += reward

    return total_reward


def update_rl_model(rl_agent, responses, abilities, batch_size=32):
    reward = compute_reward(responses, abilities)

    updated_theta_k = update_learner_ability(responses, abilities)

    next_state = np.array([list(updated_theta_k.values())]).reshape(1, -1)
    done = False

    rl_agent.remember(list(responses.keys()), reward, next_state, done)

    if len(rl_agent.memory) > batch_size:
        rl_agent.replay(batch_size)

    rl_agent.state = next_state

    return updated_theta_k
