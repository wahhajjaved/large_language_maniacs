# AFeature Extraction for Mercari Price Suggestion Competition 
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt
import numpy as np
import pandas as pd
import string
invalidChars = set(string.punctuation)

"""Read CSV and put each column into a list."""
def readFile(filename):
    df = pd.read_csv(filename)     

    # Turn each column into a list
    item_description = df['item_description'].tolist()
    item_name = df['name'].tolist()
    category_name = df['category_name'].tolist()
    brand_name = df['brand_name'].tolist()
    shipping = df['shipping'].tolist()
    item_conds = df['item_condition_id'].tolist()
    #print item_description

    # Verify the lengthts of the lists
    # Each list is of length 1482535! 
    #print len(item_description)
    #print len(item_name)
    #print len(category_name)
    #print len(brand_name)
    #print len(shipping)

    return df, item_description, item_name, category_name, brand_name, shipping, item_conds

"""Fill in names for as descriptions for items with no descriptions. """
def cleanDescriptions(item_descript, item_name):
    count = 0
    for t in range(len(item_descript)):
        if item_descript[t] == "No description yet":
            item_descript[t] = item_name[t]
    return item_descript
    #print count
        
"""Currently removes unnecessary punctuation"""
def preProcess(item_descript, item_name, df, name, brand):
    
    df['rev'] = df['item_description'].astype(str)
    raw_descript = df['rev'].tolist()

    df['temp_brand'] = df['brand_name'].astype(str)
    raw_brand = df['temp_brand'].tolist()

    df['temp_name'] = df['name'].astype(str)
    raw_name = df['name'].astype(str)

    # Fill in item name for items with no description yet
    temp_descript = cleanDescriptions(raw_descript, item_name)
    final_list = []
    foundChar = False

    # For every item description
    for i in range(len(temp_descript)):

        # Split by space
        temp_helper = temp_descript[i].split()
        for u in range(len(temp_helper)):
            split_words = []
            # Turn every word to lower case. 
            temp_helper[u] = temp_helper[u].lower()
                            
            # If the last char in a word is punctuation
            if temp_helper[u][-1:] in invalidChars:
               word = temp_helper[u][:-1]
               temp_helper[u] = word       
           # elif temp_helper[u][-1:] not in invalidChars:
           #     continue

           # Split words with - or /
            if "-" in temp_helper[u]:
                comboWord = temp_helper[u].split("-")
                foundChar = True
            elif "/" in temp_helper[u]:
                comboWord = temp_helper[u].split("/")
                foundChar = True
            
            if foundChar:
                foundChar = False
                # Remove the original entry 
                del temp_helper[u]
                # Append the splits to the end of that entry
                for part in comboWord:
                    temp_helper.append(part)
                comboWord = []

            # append name and brand
            # assuming naming and branding is uniform 
            # NEEDS TESTING
            # Check if blank brands are ""
            # Check if brand is being appended to the list properly
            # Check if name is being appended to the list properly. 
            if raw_brand[i] == "":
                temp_helper.append(raw_brand[i].lower())
            if temp_descript[i] != raw_name[i]:
                temp_helper.append(raw_name[i].lower())


        final_list.append(temp_helper)

    return final_list

def getMostFrequentWords (final_list):
    words = {}
    for sentence in final_list:
        for word in sentence:
            if word not in words:
                words[word] = 1
            else:
                words[word] += 1
    del words[""]
    # Sort word list
    freq_words = sorted(words, key = words.get, reverse = True)

    # Get most frequent words
    top_thousands = freq_words[:1000]   

    return top_thousands
    #for item in top_thousands:
     #   print item 

# Get a count of the category types
def countCategories (cat_name):
    categories = {}
    for item in cat_name:
        if item not in categories:
            categories[item] = 1
        else:
            categories[item] += 1
    
    for thing in categories:
        print str(thing) + " ---------------------- " + str(categories[thing])
    #print categories

def createMatrix(freq_words, cat_names, shipping, item_condition, brand_names, item_des):
    # Conditions
    conds = []
    for cond in item_condition:
        condition_of_item = []
        if cond == 1: 
            for x in range(5):
                if x == 0:
                    condition_of_item.append(1)
                else:
                    condition_of_item.append(0)
        elif cond == 2: 
            for x in range(5):
                if x == 1:
                    condition_of_item.append(1)
                else:
                    condition_of_item.append(0)
        elif cond == 3: 
            for x in range(5):
                if x == 2:
                    condition_of_item.append(1)
                else:
                    condition_of_item.append(0)
        elif cond == 4: 
            for x in range(5):
                if x == 3:
                    condition_of_item.append(1)
                else:
                    condition_of_item.append(0)
        elif cond == 5: 
            for x in range(5):
                if x == 4:
                    condition_of_item.append(1)
                else:
                    condition_of_item.append(0)

        # Binarize item description
        # 1 if it term is in description, 0 otherwise

        descriptions = []
        for item in item_des:
            desc_vect = []
            for term in freq_words:
                if term in item:
                    desc_vect.append(1)
                else:
                    desc_vect.append(0)
            descriptions.append(desc_vect)




            
        # append condition_of_item to corresponding training example
        # Length should match the list
        conds.append(condition_of_item)
    print len(conds)
    print len(descriptions)

if __name__ == "__main__":
    filename = "/mnt/c/Users/Aumit/Documents/GitHub/kaggle-mercari/train.csv"
    df, item_des, item_name, cat_name, brand_name, shipping, item_conds  = readFile(filename)
    fin_list = preProcess(item_des, item_name, df, item_name, brand_name)

    #countCategories(cat_name)

    freq_words = getMostFrequentWords(fin_list)
    #createMatrix(freq_words, cat_name, shipping, item_conds, brand_name, fin_list)
   
    # Verify that puncuation was properly removed.
    for y in range(10):
       print fin_list[y]

    print 
    print 
    print "Most frequent words"
    for terms in freq_words:
        print terms

    #cleanDescriptions(item_des, item_name)
