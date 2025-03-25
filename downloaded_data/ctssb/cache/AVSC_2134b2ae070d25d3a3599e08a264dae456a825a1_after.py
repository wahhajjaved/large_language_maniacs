#graphlab

#from readers import *
from graphlab import recommender, SFrame, aws

aws.set_credentials('AKIAIWD7RQTJXCCB72BA', 'E0/g0PtP7d9jkjrSyOKmQNpVKXm6FajpF34A55tN')

def test_graphlab():
    url='http://s3.amazonaws.com/GraphLab-Datasets/movie_ratings/training_data.csv'
    ''' test the graphlab install '''
    data = SFrame(url)

    m1 = recommender.matrix_factorization.create(data, user='user', item='movie',
            D=7, regularizer=0.05, nmf=True,use_bias=False)
                                        
    m2 = recommender.item_similarity.create(data, user='user', item='item',
                                               similarity_type='jaccard')        
                                               