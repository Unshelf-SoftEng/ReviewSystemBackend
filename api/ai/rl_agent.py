import pickle
import numpy as np
from collections import deque
from tensorflow.keras import Sequential, Input
from tensorflow.keras.layers import Dense
from tensorflow.keras.optimizers import Adam
from api.models import RLAgentState, Question, AssessmentResult, User, Category
import random
import os
import math

os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'


class DQNAgent:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(DQNAgent, cls).__new__(cls, *args, **kwargs)
            cls._instance._initialize_agent()
        return cls._instance

    def _initialize_agent(self):
        self.state_size = 19
        self.action_size = 1  # Q-value for selection score
        self.memory = deque(maxlen=2000)
        self.gamma = 0.95
        self.epsilon = 1.0
        self.epsilon_min = 0.01
        self.epsilon_decay = 0.995
        self.learning_rate = 0.001
        self.model = self._build_model()
        self.state = np.zeros(self.state_size)
        self.load_state_from_db()

    def _build_model(self):
        model = Sequential([
            Input(shape=(self.state_size,)),
            Dense(24, activation='relu'),
            Dense(24, activation='relu'),
            Dense(self.action_size, activation='linear')
        ])
        model.compile(loss='mse', optimizer=Adam(self.learning_rate))
        return model

    def save_state_to_db(self):
        print('Saving model to db')
        model_weights = pickle.dumps(self.model.get_weights())
        state = self.state.tolist()
        memory = pickle.dumps(list(self.memory))  # Convert deque to list first

        RLAgentState.objects.update_or_create(
            pk=1,
            defaults={
                'state': state,
                'model_weights': model_weights,
                'memory': memory
            }
        )

    def load_state_from_db(self):
        print('Loading model from db')
        try:
            agent_state = RLAgentState.objects.get(pk=1)
            self.state = np.array(agent_state.state)
            self.model.set_weights(pickle.loads(agent_state.model_weights))

            if agent_state.memory:
                self.memory = deque(pickle.loads(agent_state.memory), maxlen=2000)

        except RLAgentState.DoesNotExist:
            pass

    def get_batch_scores(self, state_matrix):
        """
        Get scores for a batch of states with epsilon-greedy exploration
        Args:
            state_matrix: 2D numpy array of shape (n_questions, state_size)
        Returns:
            1D array of scores shaped (n_questions)
        """
        scores = self.model.predict(state_matrix, verbose=0).flatten()

        if self.epsilon > 0:
            random_mask = np.random.rand(len(scores)) < self.epsilon
            scores[random_mask] = np.random.rand(np.sum(random_mask))

        return scores

    def remember(self, state, reward, next_state, done):
        self.memory.append((state, reward, next_state, done))

    def replay(self, batch_size):

        if len(self.memory) < batch_size:
            return

        minibatch = random.sample(self.memory, batch_size)

        for state, reward, next_state, done in minibatch:
            target = reward
            if not done:
                predicted = self.model.predict(next_state.reshape(1, -1), verbose=0)
                target += self.gamma * predicted[0][0]

            self.model.fit(state.reshape(1, -1), np.array([target]), verbose=0)

        self.save_state_to_db()

        # Epsilon decay
        if self.epsilon > self.epsilon_min:
            self.epsilon *= self.epsilon_decay


def generate_quiz_with_rl(rl_agent, abilities, categories, total_questions):
    all_questions = Question.objects.filter(category__in=categories)
    state_matrix = np.zeros((len(all_questions), 19))
    ability_values = [abilities.get(cat.name, 0) for cat in categories]

    for i, q in enumerate(all_questions):
        state_matrix[i, :9] = ability_values
        state_matrix[i, 9] = q.elo_difficulty
        state_matrix[i, 10 + q.category.id - 1] = 1

    scores = rl_agent.get_batch_scores(state_matrix)
    top_indices = np.argsort(-scores)[:total_questions]

    return [all_questions[int(i)] for i in top_indices]


def update_rl_model(rl_agent, assessment_id, user, batch_size=32):
    user: User = user
    result = AssessmentResult.objects.filter(assessment__id=assessment_id, user=user).first()
    if not result:
        return {}

    answers = result.answers.all()
    if not answers:
        return {}

    # Map to UserAbility instances (so we can update their elo_ability)
    ability_map = {ua.category.id: ua for ua in user.user_abilities.all()}
    categories = Category.objects.all()

    total_reward = 0
    state_transitions = []

    for answer in answers:
        question = answer.question
        category = question.category
        category_id = category.id

        user_ability = ability_map.get(category_id)
        if user_ability is None:
            continue  # skip if no UserAbility yet

        user_elo = user_ability.elo_ability
        difficulty = question.elo_difficulty
        correctness = answer.is_correct

        k = 32
        num_choices = 4

        # Shifted logistic model (with 1/4 guessing base)
        base_probability = 1 / num_choices
        logistic_component = 1 / (1 + math.exp(-(user_elo - difficulty)))
        expected = base_probability + (1 - base_probability) * logistic_component

        reward = k * (correctness - expected)
        total_reward += reward

        # Update UserAbility's Elo rating
        print('Update user elo rating');
        user_ability.elo_ability = round(user_elo + reward)
        user_ability.save()  # Save immediately

        # Build RL state
        ability_vector = np.array([
            ability_map.get(cat.id, None).elo_ability if ability_map.get(cat.id) else 0
            for cat in sorted(categories, key=lambda x: x.id)[:9]
        ], dtype=np.float32)

        difficulty_array = np.array([difficulty], dtype=np.float32)

        one_hot = np.zeros(9, dtype=np.float32)
        if category_id <= 9:
            one_hot[category_id - 1] = 1.0

        state = np.concatenate([
            ability_vector,
            difficulty_array,
            one_hot
        ])

        state_transitions.append((state, reward))

    # Train the RL agent
    for state, reward in state_transitions:
        next_state = state.copy()
        rl_agent.remember(state, reward, next_state, False)

    rl_agent.replay(batch_size)

    # Return the full original ability_map (updated objects)
    return ability_map
