import requests, json

def split_foods(text):
    words = text.split(':',1)[1]
    return split_text(words)

def split_text(text):
    words = text.split(',')
    return caloric_values(words)



def caloric_values(foods):
	input_calorie = []
	for input_string in foods:
		url_format = input_string.replace(' ', '%20')
		r = requests.get("https://api.nutritionix.com/v1_1/search/%s?results=0:20&fields=item_name,brand_name,item_id,nf_calories&appId=3f8d7092&appKey=fe9f67745b9e3756438f5d6edf6f6a03"%(url_format))
		j = r.json()
		caloric_value = j['hits'][0]['fields']['nf_calories']
		input_calorie.append(caloric_value)
	return list(zip(foods, input_calorie))

def get_meals(string):
	return split_foods(string)
