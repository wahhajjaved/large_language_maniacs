"""Contains the editable strings for the Website"""

def actor_instructions():
    return "After you press continue, you will be given a choice of 5 different phrases." +\
           " Once you select a phrase by clicking it you will have a limited time act it out." +\
           " If the phrase is guess successfully you will be asked to choose a new phrase." +\
           " The more phrases that are guessed correctly, the more points you score."

def viewer_instructions():
    return "After the Actor has selected a phrase, you will have a limited time to guess it." +\
           " Look at the hologram infront of you to see what the actor is doing." +\
           " The faster you guess the phrase the more points you get." +\
           " You will be given some information about the current word or phrase to help you guess."

def actor_none():
    return "Requested page could not be loaded as no actor is present." +\
           " Please ensure an Actor has signed in using the correct session key."

def invalid_session():
    return "Invalid session ID has been provided."