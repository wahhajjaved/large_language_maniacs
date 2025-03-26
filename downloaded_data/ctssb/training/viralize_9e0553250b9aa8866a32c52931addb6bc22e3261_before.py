from twitter import *
import os


def publish(data):
    CONSUMER_KEY='PioawmiVQLIGSQCdLfN8wbgnJ'
    CONSUMER_SECRET='41SHzZ6uAGZoVGPCXGC3mPlZmzCan0m30xYvOK0EjdfZEJRFs1'
    MY_TWITTER_CREDS = os.path.expanduser('.twitter_credentials')
    if not os.path.exists(MY_TWITTER_CREDS):
        oauth_dance("Viralise", CONSUMER_KEY, CONSUMER_SECRET,
                    MY_TWITTER_CREDS)

    oauth_token, oauth_secret = read_token_file(MY_TWITTER_CREDS)

    t = Twitter(auth=OAuth(
                oauth_token, oauth_secret, CONSUMER_KEY, CONSUMER_SECRET))
    if len(data['channel']) <140:
        return "Message is %s long.Only 140 allowed"%len(data['channel'])
    try:
        #t.statuses.update(status=data['message'])
        print "sending"
    
        return 'Successfully sent to Twitter'
    except:
        return 'Error: Could not post to twitter'
