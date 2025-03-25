import tensorflow as tf
import numpy as np
import debugtools

# Copies one set of variables to another.
# Used to set worker network parameters to those of global network.
def update_target_graph(from_scope,to_scope):
    from_vars = tf.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES, from_scope)
    to_vars = tf.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES, to_scope)

    op_holder = []
    for from_var,to_var in zip(from_vars,to_vars):
        op_holder.append(to_var.assign(from_var))
    return op_holder

class BasicAgent():
    '''
    Uses a 1-hidden-layer dense NN to compute probability of going UP,
    then samples using that probability to decide its action.

    * arguments:

    hidden_size, default=100
        controls the number of nodes in the hidden layer.

    learning_rate, default=0.01
        controls the learning rate of the optimiser used for training.

    * comments:

    uses tf.AdamOptimiser for its training step.

    '''
    def __init__(self, hidden_size=100, learning_rate=0.01):

        def weight_variable(shape, name):
            initial = tf.truncated_normal(shape, stddev=0.05)
            return tf.Variable(initial, name=name)

        self.W1 = weight_variable([80*80, hidden_size], "W1")
        self.W2 = weight_variable([hidden_size, 1], "W2")

        self.frames  = tf.placeholder(shape=(None, 80*80), dtype=tf.float32, name="frames_in")  # flattened diff_frame
        self.actions = tf.placeholder(shape=(None,),     dtype=tf.float32, name="action_in")  # 1 if agent went UP, 0 otherwise
        self.rewards = tf.placeholder(shape=(None,),     dtype=tf.float32, name="reward_in")  # 1 if frame comes from a won game, -1 otherwise

        self.hidden_layer = tf.nn.relu(tf.matmul(self.frames, self.W1), name="hidden_layer")
        self.output_layer = tf.nn.sigmoid(tf.matmul(self.hidden_layer, self.W2), name="output_layer")

        # loss = - sum over i of reward_i * p(action_i | frame_i)
        self.loss = - tf.reduce_sum(self.rewards * (self.actions * self.output_layer + (1-self.actions)*(1-self.output_layer)), name="loss")

        self.Optimizer = tf.train.AdamOptimizer(learning_rate=learning_rate)
        self.train_step = self.Optimizer.minimize(self.loss)

    def action(self, sess, diff_frame):
        '''returns a probability of going UP at this frame'''
        feed_dict = {self.frames:diff_frame}
        predicted_action = sess.run(self.output_layer, feed_dict=feed_dict)[0,0]
        action = np.random.binomial(1, predicted_action)
        return action

    def gym_action(self, sess, diff_frame):
        return 3 + self.action(sess, diff_frame)

    def train(self, sess, diff_frames, actions, rewards):
        '''trains the agent on the data'''
        feed_dict={self.frames:diff_frames, self.actions:actions, self.rewards:rewards}
        _, loss = sess.run([self.train_step, self.loss], feed_dict=feed_dict)
        return loss
