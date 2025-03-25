from input import *

#Written by Nathan
def story():
    location1 = getWord(" Enter a location: ")
    temperature1 = getNumber(" Enter a Number: ")
    food1 = getWord (" enter food: " )
    pokemon1 =getWord(" enter a pokemon: ")
    adjective1 =getword (" enter a adjective: ")
    text = ""
    text += "One day I went to " + location1
    text += ". It was like " + temperature1
    text += " outside."    
    text +=" Then suddenly, a wild " + pokemon1
    text +=" appeared! " 
    text +="While the " + pokemon1
    text+= " ate all of the " + food1
    text +=" We all watched it wondering how it got here."
    text +=" While the pokemon ate the " + food1
    text += " we continued doing normal things." 
    text += " These things where very " + adjective1
    return text
    
