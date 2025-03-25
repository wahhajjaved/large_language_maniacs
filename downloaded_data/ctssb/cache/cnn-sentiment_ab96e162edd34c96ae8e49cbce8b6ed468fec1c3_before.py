import tensorflow as tf

def make_cnn_classifier(inputs, emb_array, dropout_rate):
    """Build the graph of the model.
    Args:
        inputs: tensor, mini-batch of word IDs for sentences
        emb_array: numpy array of shape (vocabulary_size, emb_dimension)
            used to initialize the embedding layer.
    Returns:
        logit, the output tensor of the classifier.
    """
    # Embedding layer
    embeddings = tf.get_variable('embeddings', shape=emb_array.shape,
                    initializer=tf.constant_initializer(emb_array))
    x = tf.nn.embedding_lookup(embeddings, inputs)

    # Features from convolutional layers, one per filter size
    features = []
    filter_sizes = [3, 4, 5]
    for i, filter_size in enumerate(filter_sizes):
        # Convolution
        f = tf.layers.conv1d(x, filters=100, kernel_size=3,
                                       padding='same', activation=tf.nn.relu,
                              name='conv{}'.format(i + 1))
        # Max-pooling over time
        with tf.name_scope('max-time-pool{}'.format(i + 1)):
            features.append(tf.reduce_max(f, axis=1))

    x = tf.concat(features, axis=1)

    x = tf.layers.dropout(x, rate=dropout_rate)
    logit = tf.layers.dense(x, 1)

    return logit
