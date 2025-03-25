import gym
import numpy as np

env = gym.make('CartPole-v0')
for i_episode in xrange(20):
    observation = env.reset()
    for t in xrange(100):
        env.render()
        print observation
        
        action = get_action(observation)
        s_a_count_update(observation,action)
        old_state = observation  # retain old state for updates
        
        observation, reward, done, info = env.step(action)
        
        new_state = observation
        update_sas_trans_count(old_state,action,new_state)
        trans_reward_update(old_state,action,reward,new_state)
        
        if (old_state,action) not in q_val_dict:
          q_val_dict[(old_state,action)] = 0
        
        est_q_reward = trans_reward_dict[(old_state, action, new_state)]
        # not accounting for state non-determinism
        update_Q(old_state, action, est_q_reward, new_state)  
        
        if done:
            print "Episode finished after {} timesteps".format(t+1)
            break
   
            
# function for getting action    
def get_action(state):
  if (state_count(state) == 1) or (np.random.random < 0.1): # if this is the first time seeing state, or 1 in 10(e-greedy)
    action = env.action_space.sample()                      # random action
  else:
    action = best_act_for_s(state)        
            


# state observation dict
state_count_dict = {}

# state observation counter
def state_count(state):
  if state not in state_count_dict:
    state_count_dict[state] = 1
    #q_val_dict[state] = 0 # initialize q-value for state
  else:
    state_count_dict[state] += 1
  return state_count_dict[state]
    

# state-action pair count dictionary
s_a_count_dict = {}

def s_a_count_update(state,action):
  if (state,action) not in s_a_count_dict:
    s_a_count_dict[(state,action)] = 1
  else:
    s_a_count_dict[(state,action)] += 1  
  

# dictionary for S'A'S counts, needed to track non-determinism
sas_count_dict = {}

def sas_count_update(old_state, action, new_state):
  if (old_state, action, new_state) not in sas_count_dict:
    sas_count_dict[(old_state, action, new_state)] = 1
  else:
    sas_count_dict[(old_state, action, new_state)] += 1
  
  
# for iterating s'  
s_a_to_s_dict = {}

def add_s_to_sas(old_state,action,new_state):
  if (old_state,action) not in s_a_to_s_dict:
    s_a_to_s_dict[(old_state,action)] = (new_state,)
  if new_state not in s_a_to_s_dict[(old_state,action)]:
    s_a_to_s_dict[(old_state,action)].append(new_state)
      

# create SAS transition count dictionary
trans_dict_count = {}

def update_sas_trans_count(old_state,action,new_state):
  if (old_state,action,new_state) not in trans_dict_count:
    trans_dict_count.append((old_state,action,new_state):1)              
  else:  
    trans_dict_count[(old_state,action,new_state)]+=1
  
  
# need transition reward dictionary to keep track of rewards for (s,a,s') tuples
trans_reward_dict = {}  

# transition function for rewards, code for keeping track of stochastic rewards
def trans_reward_update(old_state,action,reward,new_state):
  tdc = trans_dict_count[(old_state, action, new_state)]
  if tdc == 1:
    trans_reward_dict[(old_state, action, new_state)] == reward
  else:
    trd = trans_reward_dict[(old_state, action, new_state)]
    trans_reward_dict[(old_state, action, new_state)] == ((tdc-1)*trd + reward)/tdc 
  #return trans_reward_dict[(old_state, action, new_state)]  
  
# function for returning best action based on q_function
def best_act_for_s(state): # will arg-max our action
  high_q = 0
  high_act = ''
  for kee in q_val_dict:
    if kee[0] == state:
      if q_val_dict[kee] > high_q:
        high_q = q_val_dict[kee]
        high_act = kee[1]
  return high_act
  #print(high_q)
  #print(high_act)

# max q function, returns highest estimated q for state
def max_q(state):
  if state_count(state) == 1:
    return 0 
  else:
    return q_val_dict[(state,best_act_for_s(state))]
    
 
# dictionary of q-values
q_val_dict = {}     
     
     
# function for updating Q  
def update_Q(old_state, action, est_q_reward, new_state):
  
  learning_rate = 0.2
  discount = 0.9
  q_val_dict[(old_state,action)] = q_val_dict[(old_state,action)] + 
    learning_rate*(est_q_reward + discount*max_q(new_state) - q_val_dict[old_state]) 
  
  
# new function for updating Q(s,a) while accounting for non-determinism in sas transition

def update_Q_sa(old_state, action):

  learning_rate = 0.2
  discount = 0.9
  sas_weighting = {}
  for n_state in s_a_to_s_dict[(old_state,action)]:
    weight = sas_count_dict[(old_state,action,n_state)] / s_a_count_dict[(old_state,action)]
    sas_weighting[(old_state,action,n_state)] = weight 
  
  q_val_dict[(old_state,action)] = 0  #clear old value
  for each_sas_tup in sas_weighting:
    q_val_dict[(old_state,action)] += sas_weighting[each_sas_tup]*(q_val_dict[(old_state,action)] + 
      learning_rate*(trans_reward_dict[each_sas_tup] + discount*max_q(each_sas_tup[2]) - q_val_dict[(old_state,action)])) 
  
  