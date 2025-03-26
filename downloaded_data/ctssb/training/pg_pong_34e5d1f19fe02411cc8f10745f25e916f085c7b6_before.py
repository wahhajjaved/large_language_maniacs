import numpy as np

from policy_network import PolicyNetwork
from utils import pre_process_img
from const import ACTION_UP, ACTION_DOWN

IS_RESUME = True
GAMMA = 0.99 # reward discount

class PGAgent():
    def __init__(self, env):
        self.env = env
        self.observation = env.reset()
        self.prev_x = None
        self.net = PolicyNetwork(IS_RESUME)

        self.x_history = []
        self.h_history = []
        self.dlogp_history = []
        self.reward_history = []

    def reset(self):
        self.observation = self.env.reset()
        self.prev_x = None

    def select_action(self):
        current_x = pre_process_img(self.observation)
        self.x = current_x - (self.prev_x if self.prev_x is not None else np.zeros_like(current_x))
        self.prev_x = current_x

        self.up_prob = self.net.forward(self.x)
        self.action = ACTION_UP if np.random.uniform() < self.up_prob else ACTION_DOWN

        return self.action

    def add_history(self, reward):
        dlogp = self.action - self.up_prob

        self.x_history.append(self.x)
        self.h_history.append(self.net.h)
        self.dlogp_history.append(dlogp)
        self.reward_history.append(reward)

    def accumulate_grads(self):
        advantages = self.discount_rewards(self.reward_history)
        advantages -= np.mean(advantages)
        advantages /= np.std(advantages)

        episode_logp = advantages * self.dlogp_history
        grads = self.net.backward(
                np.vstack(self.x_history),
                np.vstack(self.h_history),
                episode_logp)
        for k in self.net.model: self.net.grads_buffer[k] += grads[k]

        self.x_history = []
        self.h_history = []
        self.dlogp_history = []
        self.reward_history = []

    # discount_rewards([0, 0, 0, 0, 1.0, 0, 0, 0, -1.0]) returns
    # [ 0.96059601, 0.970299, 0.9801, 0.99, 1., -0.970299, -0.9801, -0.99, -1.]
    def discount_rewards(self, rewards):
        discounted_rewards = np.zeros_like(rewards)
        reward_cursor = 0

        for i in reversed(range(len(rewards))):
            if rewards[i] == 0: reward_cursor = 0
            reward_cursor = reward_cursor * GAMMA + rewards[i]
            discounted_rewards[i] = reward_cursor

        return discounted_rewards

    def train_net(self):
        self.net.update(self.net.grads_buffer)

