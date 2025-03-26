def prototype_state():
    state = {}

    # Random seed
    state['seed'] = 1234

    # Logging level
    state['level'] = 'DEBUG'

    # Data
    state['source'] = ["/data/lisatmp3/bahdanau/shuffled/phrase-table.en.h5"]
    state['target'] = ["/data/lisatmp3/bahdanau/shuffled/phrase-table.fr.h5"]
    state['indx_word'] = "/data/lisatmp3/chokyun/mt/ivocab_source.pkl"
    state['indx_word_target'] = "/data/lisatmp3/chokyun/mt/ivocab_target.pkl"
    state['word_indx'] = "/data/lisatmp3/chokyun/mt/vocab.en.pkl"
    state['word_indx_trgt'] = "/data/lisatmp3/bahdanau/vocab.fr.pkl"
    state['oov'] = 'UNK'
    # TODO: delete this one
    state['randstart'] = False

    # These are end-of-sequence marks
    state['null_sym_source'] = 15000
    state['null_sym_target'] = 15000

    # These are vocabulary sizes for the source and target languages
    state['n_sym_source'] = state['null_sym_source'] + 1
    state['n_sym_target'] = state['null_sym_target'] + 1
    state['unk_sym_target'] = 1

    # This is for predicting the next target from the current one
    state['bigram'] = True

    # This for the hidden state initilization
    state['bias_code'] = True

    # This is for the input -> output shortcut
    state['avg_word'] = False

    state['eps'] = 1e-10

    # Dimensionality of hidden layers
    state['dim'] = 1000

    # Size of hidden layers' stack in encoder and decoder
    state['encoder_stack'] = 1
    state['decoder_stack'] = 1

    state['deep_out'] = True
    state['mult_out'] = False

    state['rank_n_approx'] = 100
    state['rank_n_activ'] = 'lambda x: x'

    # Hidden layer configuration
    state['enc_rec_layer'] = 'RecurrentLayer'
    state['enc_rec_gating'] = True
    state['enc_rec_reseting'] = True
    state['enc_rec_gater'] = 'lambda x: TT.nnet.sigmoid(x)'
    state['enc_rec_reseter'] = 'lambda x: TT.nnet.sigmoid(x)'

    state['dec_rec_layer'] = 'RecurrentLayer'
    state['dec_rec_gating'] = True
    state['dec_rec_reseting'] = True
    state['dec_rec_gater'] = 'lambda x: TT.nnet.sigmoid(x)'
    state['dec_rec_reseter'] = 'lambda x: TT.nnet.sigmoid(x)'

    # Representation from hidden layer
    state['take_top'] = True

    # Hidden-to-hidden activation function
    state['activ'] = 'lambda x: TT.tanh(x)'

    # This one is bias applied in the recurrent layer. It is likely
    # to be zero as MultiLayer already has bias.
    state['bias'] = 0.

    # This one is bias at the projection stage
    # TODO fully get what is it needed for
    state['bias_mlp'] = 0.

    # Specifiying the output layer
    state['maxout_part'] = 2.
    state['unary_activ'] = 'Maxout(2)'

    # Weight initialization parameters
    state['rec_weight_init_fn'] = 'sample_weights_orth'
    state['weight_init_fn'] = 'sample_weights_classic'
    state['rec_weight_scale'] = 1.
    state['weight_scale'] = 0.01

    # Dropout in output layer
    state['dropout'] = 1.
    # Dropout in recurrent layers
    state['dropout_rec'] = 1.

    # Random weight noise regularization settings
    state['weight_noise'] = False
    state['weight_noise_rec'] = False
    state['weight_noise_amount'] = 0.01

    # Threshold to cut the gradient
    state['cutoff'] = 1.
    # TODO: what does it do?
    state['cutoff_rescale_length'] = 0.

    # Choose optimization algo
    state['algo'] = 'SGD_adadelta'

    # Adagrad setting
    state['adarho'] = 0.95
    state['adaeps'] = 1e-6

    # Learning rate stuff for SGD
    state['patience'] = 1
    state['lr'] = 1.
    state['minlr'] = 0

    # Batch size
    state['bs']  = 64
    state['sort_k_batches'] = 10

    # Maximum sequence length
    state['seqlen'] = 30
    state['use_infinite_loop'] = True

    # Sampling hook settings
    state['n_samples'] = 3
    state['n_examples'] = 3

    # Activates bug fix
    state['check_first_word'] = True

    # Specifies whether old model should be reloaded first
    state['reload'] = True

    # Number of batches to process
    state['loopIters'] = 3000000
    # Maximum number of minutes to run
    state['timeStop'] = 24*60*7
    # Error level to stop at
    state['minerr'] = -1

    # Data iterator options
    state['reset'] = -1
    state['shuffle'] = False
    state['cache_size'] = 0

    # Frequency of training error reports (in number of batches)
    state['trainFreq'] = 1
    # Frequency of running hooks
    state['hookFreq'] = 13
    # Validation frequency
    state['validFreq'] = 500
    # Model saving frequency (in minutes)
    state['saveFreq'] = 10

    # Turns on profiling of training phase
    state['profile'] = 0

    # Raise exception if nan
    state['on_nan'] = 'raise'

    # Default paths
    state['prefix'] = 'phrase_'

    # When set to 0 each new model dump will be saved in a new file
    state['overwrite'] = 1

    return state

def prototype_sentence_state():
    state = prototype_state()

    state['target'] = ["/u/chokyun/tmp3/mt/vocab.30k/bitexts.selected/binarized_text.shuffled.fr.h5"]
    state['source'] = ["/u/chokyun/tmp3/mt/vocab.30k/bitexts.selected/binarized_text.shuffled.en.h5"]
    state['indx_word'] = "/u/chokyun/tmp3/mt/vocab.30k/bitexts.selected/ivocab_source.pkl"
    state['indx_word_target'] = "/u/chokyun/tmp3/mt/vocab.30k/bitexts.selected/ivocab_target.pkl"
    state['word_indx'] = "/u/chokyun/tmp3/mt/vocab.30k/bitexts.selected/vocab.en.pkl"
    state['word_indx_trgt'] = "/u/chokyun/tmp3/mt/vocab.30k/bitexts.selected/vocab.fr.pkl"

    state['null_sym_source'] = 30000
    state['null_sym_target'] = 30000

    state['n_sym_source'] = state['null_sym_source'] + 1
    state['n_sym_target'] = state['null_sym_target'] + 1

    state['seqlen'] = 50

    state['dim'] = 2000
    state['rank_n_approx'] = 620
    state['bs']  = 80

    state['prefix'] = 'sentence_'

    return state

def prototype_autoenc_state():
    state = prototype_sentence_state()
    state['target'] = ["/data/lisatmp3/bahdanau/mt/binarized_text.shuffled.en.h5"]
    state['indx_word_target'] = state['indx_word']
    state['word_indx_trgt'] = state['word_indx']
    return state
