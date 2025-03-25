'''
Input: city_name, hotel_name

Output: what is a map: {attribute -> {0 -> %, 1 -> %, 2 -> %, 3 -> %, 4 -> %}}

process: city_name and hotel_name are part of elastic search attributes.
query: elastic search query results in [elastic_search_obj]

processing: 
    Input: [elastic search object]
    output: attribute_path -> sentiment -> number of people
    output: attribute_path -> adjective -> number of people
    for each object:
        find attribute path
        for that path, update the sentiment.

'''

import sys
import json
sys.path.insert(0, 'scripts/lib/')
import pprint
import operator
import elastic_search as es
from random import randint

hash_tag_delim = '_'
hash_tag_prefix = ''

def create_hash_tag(attr, adj):
    return hash_tag_prefix + adj.lower() + hash_tag_delim + attr.lower()

negative_adjectives = json.loads(open('data/tree-data/attribute_adjective_negative.json', 'r').read())
negative_adjectives_common = ['bad', 'ugly', 'expensive', 'unhelpful', 'unfriendly', 'unfree']
positive_adjectives_common = ['good', 'great', 'awesome', 'cheap', 'helpful']
neutral_adjectives = []

attribute_seed = json.loads(open('data/tree-data/percolate_8.json', 'r').read())
positive_adjectives = json.loads(open('data/tree-data/attribute_adjective_positive.json', 'r').read())



def find_random_negative(attr):
    index = randint(0, len(negative_adjectives[attr]) - 1)
    return negative_adjectives[attr][index]

def find_random_positive(attr):
    index = randint(0, len(positive_adjectives[attr]) - 1)
    return positive_adjectives[attr][index]

def find_random_neutral():
    return 'so so'

def find_abs_path(search_node):
#    if root_node['next'] == {}:
#        return False
#    for node in root_node['next']:
#        if node == search_node:
#            path.append(search_node)
#            return True
#        if find_abs_path(search_node, root_node['next'][node], path):
#            path.append(node)
#            return True
    return search_node

def find_path(item):
    path_obj = {}
    for attr_root in item['attribute_list']:
        leaf_name = attr_root['value']
        path = find_abs_path(leaf_name)
        score = item['score'][leaf_name]
        path_obj[str(path)] = score
    return path_obj

def find_sentiment(item):
    result = {}
    for leaf_attr in item['sentiment']:
        path = find_abs_path(leaf_attr)
        result[str(path)] = item['sentiment'][leaf_attr]
    return result

def find_adjective(item):
    result = {}
    for leaf_attr in item['adjective_list']:
        path = find_abs_path(leaf_attr)
        result[str(path)] = item['adjective_list'][leaf_attr]
    return result

def insert_or_increment(out, path_dict, sentiment_dict):
    for path in path_dict:
        if path not in out:
            out[path] = {}
        score = path_dict[path]
        sent = sentiment_dict[path]
        if sent not in out[path]:
            out[path][sent] = 0
        out[path][sent] += score
        
def insert_or_increment_adjective(out, path_dict, adjective_dict):
    for path in path_dict:
        if path not in out:
            out[path] = {}
        #score = path_dict[path]
        if len(adjective_dict[path]) > 0:
            adj = adjective_dict[path][0]
            adj_score = adjective_dict[path][1]
            if adj in out[path]:
                out[path][adj] = out[path][adj] + adj_score
            else:
                out[path][adj] = adj_score

'''
input: city_name, hotel_id
output: 
    output_sentiment: path -> sentiment -> score
    output_adjective: path -> adjective -> score
'''
def find_city_hotel_attributes(city_name, hotel_id):
    elastic_results = es.find_city_hotel_reviews(city_name, hotel_id)
    output_sentiment = {}   # format is: 
    output_adjective = {}   # format is: 
    for item in elastic_results['hits']['hits']:
        item = item['_source']
        path_dict = find_path(item)
        #print 'path_dict: ' +  str(path_dict)
        sentiment_dict = find_sentiment(item)
        #print 'sentiment_dict: ' + str(sentiment_dict)
        adjective_dict = find_adjective(item)
        #print 'adjective_dict: ' + str(adjective_dict)
        insert_or_increment(output_sentiment, path_dict, sentiment_dict)
        insert_or_increment_adjective(output_adjective, path_dict, adjective_dict)
        
    return output_sentiment, output_adjective

def find_city_hotel_images(city_name, hotel_id):
    elastic_results = es.find_city_hotel_images(city_name, hotel_id)
    output = {}   # format is: path -> [url, score]
    for item in elastic_results['hits']['hits']:
        item = item['_source']
        url = item['url']
        score = item['score']
        path = map(lambda x: x['value'], item['attributes'])
        #print 'path: ' + str(path)
        path_s = str(path[len(path) - 1])
        if path_s not in output:
            output[path_s] = []
        output[path_s].append((url, score))
    for path in output:
        output[path].sort(key=lambda x: x[1], reverse=True)
    return output

def find_city_all_hotels_reviews_images(city_name):
    output_sentiment, output_adjective = find_city_all_hotels_attributes(city_name)
    output_images = find_city_all_hotels_images(city_name)
    output_c = {}
    for hotel_id in output_sentiment:
        if hotel_id in output_images:
            output_c[hotel_id] = {}
            for path in output_sentiment[hotel_id]:
                output_c[hotel_id][path] = {}
                output_c[hotel_id][path]['reviews'] = output_sentiment[hotel_id][path]
                if path in output_images[hotel_id]:
                    output_c[hotel_id][path]['images'] = output_images[hotel_id][path]
        else:
            output_c[hotel_id] = output_sentiment[hotel_id]
    return output_c

def find_city_all_hotels_attributes(city_name):
    elastic_results = es.find_city_reviews(city_name)
    output_sentiment = {}   # format is: hotel_id -> path -> sentiment -> score
    output_adjective = {}   # format is: hotel_id -> path -> adjective -> score
    for item in elastic_results['hits']['hits']:
        item = item['_source']
        hotel_id = item['hotel_id']
        if hotel_id not in output_sentiment:
            output_sentiment[hotel_id] = {}
        if hotel_id not in output_adjective:
            output_adjective[hotel_id] = {}
        path_dict = find_path(item)
        #print 'path_dict: ' +  str(path_dict)
        sentiment_dict = find_sentiment(item)
        #print 'sentiment_dict: ' + str(sentiment_dict)
        adjective_dict = find_adjective(item)
        #print 'adjective_dict: ' + str(adjective_dict)
        insert_or_increment(output_sentiment[hotel_id], path_dict, sentiment_dict)
        insert_or_increment_adjective(output_adjective[hotel_id], path_dict, adjective_dict)

    return output_sentiment, output_adjective

def find_city_all_hotels_images(city_name):
    elastic_results = es.find_city_images(city_name)
    output = {}   # format is: hotel_id -> path -> [(url, score)]
    for item in elastic_results['hits']['hits']:
        item = item['_source']
        hotel_id = str(item['hotel_id'])
        if hotel_id not in output:
            output[hotel_id] = {}
        url = item['url']
        score = item['score']
        path = map(lambda x: x['value'], item['attributes'])
        path_s = str(path[len(path) - 1])
        if path_s not in output[hotel_id]:
            output[hotel_id][path_s] = []
        output[hotel_id][path_s].append((url, score))
        
    for hotel_id in output:
        for path in output[hotel_id]:
            output[hotel_id][path].sort(key=lambda x: x[1], reverse=True)

    return output

def find_sum_over_sentiment(output_sentiment):
    output_sentiment_sum = {}
    for hotel_id in output_sentiment:
        output_sentiment_sum[hotel_id] = {}
        for attribute in output_sentiment[hotel_id]:
            sentiment_dist = output_sentiment[hotel_id][attribute]
            sentiment_values = map(lambda x: x[1], sentiment_dist.items())
            sentiment_values_sum = reduce(lambda x, y: x+y, sentiment_values)
            output_sentiment_sum[hotel_id][attribute] = sentiment_values_sum
    return output_sentiment_sum

def sort(output_sentiment_sum, candidate_attribute):
    hotel_sentiment_map = {}
    for hotel_id in output_sentiment_sum:
        for attr in output_sentiment_sum[hotel_id]:
            if attr == candidate_attribute:
                hotel_sentiment_map[hotel_id] = output_sentiment_sum[hotel_id][attr]
    return sorted(hotel_sentiment_map.items(), key=operator.itemgetter(1), reverse=True)
                
def find_city_attribute_top_hotels(city_name, attribute):
    print 'finder:: ' + city_name + ' ; ' + attribute
    output_sentiment, output_adjective = find_city_all_hotels_attributes(city_name)
    output_sentiment_sum = find_sum_over_sentiment(output_sentiment)
    output_sentiment_sort = sort(output_sentiment_sum, attribute)
    return output_sentiment_sort, output_sentiment, output_adjective

def find_city_location_hotels(lat, lon):
    print 'finder:: ' + str(lat) + ' ; ' + str(lon)
    elastic_results = es.find_location_hotels(lat, lon)
    output = []
    for item in elastic_results['hits']['hits']:
        item = item['_source']
        output.append(item)
    return output

'''
output: 
    [hash_tags]
    {attribute -> [hash_tags]}
'''
def find_hotel_hashtags(city_name, hotel_id):
    most_talked_about = {}
    most_talked_about_arr = {}
    output_sentiment, output_adjective = find_city_hotel_attributes(city_name, hotel_id)
    for path in output_sentiment:
        s = sum(output_sentiment[path].values())
        most_talked_about[path] = s
    most_talked_about_arr = most_talked_about.items()
    #print 'most: ' + str(most_talked_about_arr[hotel_id])
    most_talked_about_arr.sort(key=lambda x: x[1], reverse=True)
    
    output = {} # attribute -> [(hashtag, score)]
    for attr, attr_score in most_talked_about_arr:
        adjective_values = output_adjective[attr].items()
        if adjective_values == []:
            print 'No adjective found for: ' + str(attr)
            continue
        adj, adj_score = adjective_values[0]
        hash_tag = hash_tag_prefix + adj + hash_tag_delim + attr
        hash_score = attr_score * adj_score
        if attr not in output:
            output[attr] = []
        output[attr].append((hash_tag, hash_score))
    for attr in output:
        output[attr].sort(key=lambda x: x[1], reverse=True)
    return output_sentiment, output_adjective, output

def filter_adjective(adjective_values, negative_adjectives):
    result = []
    for adj, adj_score in adjective_values:
        if adj not in negative_adjectives:
            result.append((adj, adj_score))
    return result

'''
input: city_name
level 1: 
output: hashtag -> [hotel_id]
'''
def find_city_hashtags(city_name):
    output = {} # hashtag -> [(hotel_id, score)]
    most_talked_about = {}
    most_talked_about_arr = {}
    output_sentiment, output_adjective = find_city_all_hotels_attributes(city_name)
    for hotel_id in output_sentiment:
        if hotel_id not in most_talked_about:
            most_talked_about[hotel_id] = {}
        for path in output_sentiment[hotel_id]:
            s = sum(output_sentiment[hotel_id][path].values())
            most_talked_about[hotel_id][path] = s
        most_talked_about_arr[hotel_id] = most_talked_about[hotel_id].items()
        #print 'most: ' + str(most_talked_about_arr[hotel_id])
        most_talked_about_arr[hotel_id].sort(key=lambda x: x[1], reverse=True)
    
    for hotel_id in most_talked_about_arr:
        #print 'most: ' + str(most_talked_about_arr[hotel_id])
        for attr, attr_score in most_talked_about_arr[hotel_id]:
            adjective_values = output_adjective[hotel_id][attr].items()
            if adjective_values == []:
                print 'No positive adjective found for: ' + str(attr)
                continue
            filtered_adjectives = filter_adjective(adjective_values, negative_adjectives_common)
            if filtered_adjectives == []:
                print 'No positive adjective found for: ' + str(attr)
                continue
            adj, adj_score = filtered_adjectives[0]
            # what is the sentiment of this adj.
            hash_tag = create_hash_tag(adj, attr)
            hash_score = attr_score * adj_score
            if hash_tag not in output:
                output[hash_tag] = []
            output[hash_tag].append((hotel_id, hash_score))
    for hash_tag in output:
        output[hash_tag].sort(key=lambda x: x[1], reverse=True)
    return output

    
if __name__ == "__main__":
    result = {}
    arg_count = 1
    search_kind = sys.argv[arg_count]
    arg_count += 1
    search_type = sys.argv[arg_count]
    arg_count += 1
    if search_kind == 'reviews':
        if search_type == 'city_hotel':
            assert(len(sys.argv) >= 4)
            result = find_city_hotel_attributes(sys.argv[arg_count], sys.argv[arg_count + 1])
        else:
            if search_type == 'city_attribute':
                assert(len(sys.argv) >= 4)
                result, res2, res3 = find_city_attribute_top_hotels(sys.argv[arg_count], sys.argv[arg_count + 1])
            else:
                if search_type == 'loc':
                    assert(len(sys.argv) >= 4)
                    result = find_city_location_hotels(sys.argv[arg_count], sys.argv[arg_count + 1])
                else:
                    if search_type == 'city_hash':
                        result = find_city_hashtags(sys.argv[arg_count])
                    else:
                        raise Exception('invalid search type: ' + search_type)
    else:
        if search_kind == 'images':
            if search_type == 'city_hotel':
                assert(len(sys.argv) >= 4)
                result = find_city_hotel_images(sys.argv[arg_count], sys.argv[arg_count + 1])
            else:
                if search_type == 'city':
                    assert(len(sys.argv) >= 4)
                    result = find_city_all_hotels_images(sys.argv[arg_count])
        else:
            if search_kind == 'both':
                result = find_city_all_hotels_reviews_images(sys.argv[arg_count])
    pp = pprint.PrettyPrinter(depth=4)
    pp.pprint(result)