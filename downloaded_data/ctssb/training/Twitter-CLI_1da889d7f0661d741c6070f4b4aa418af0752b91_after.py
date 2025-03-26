from constants import SELECT, TODAY, BORDER, BORDER_LEN
from utils import *
from queries import * 

def compose_tweet(session, user, menu_func=None, replyto=None):
    """ Generates a new tweet and inserts it into the database
    Also inserts any hashtags into hashtags and mentions tables

    :param session: Session object 
    :param user: logged in user's id
    :param replyto (optional): the user id of who the tweet is replying to
    """
    new_tweet = create_tweet(session, user, menu_func, replyto)
 
    confirm = validate_yn("Confirm tweet? y/n: ", session)
    if confirm in ["n", "no"]:
        print("Tweet cancelled.")
        return None if menu_func is None else menu_func() 
             
    insert_tweet(session.get_conn(), new_tweet.get_values())
    new_tweet.insert_terms()

    print(BORDER)
    print_string("Tweet %d created - %s." % (new_tweet.tid(), new_tweet.tdate()))
    print_string("Hashtags mentioned: %s" % (new_tweet.get_terms()))
    print(BORDER)

    press_enter()

def create_tweet(session, user, menu_func, replyto):
    """Gets info for new tweet and creates new Tweet object

    :param session: Session object
    :param user: logged in user id
    :param menu_func: function to return to if user quits
    :param replyto: id of user to replyto or None
    """
    text = validate_str("Enter tweet: ", session, menu_func=menu_func)
    print('\n' + BORDER)

    writer = user
    tid = generate_tid(session.get_conn())
    date = TODAY
    replyto = replyto
    rt_user = None
    data = [tid, writer, date, text, replyto, rt_user]
    new_tweet = Tweet(session, user, data)
    new_tweet.display()
    new_tweet.set_terms()

    if not new_tweet.valid_terms():
        return create_tweet(session, user, menu_func, replyto)
    
    return new_tweet

   
def generate_tid(conn):
    """Generates a new unique tweet id
    
    :param conn: session connection
    """
    curs = conn.cursor()
    select(curs, 'tweets')
    new_tid = len(curs.fetchall()) + 1
    
    while tid_exists(curs, new_tid): 
        new_tid += 1
    curs.close()

    return new_tid


def search_tweets(session, user):
    """Match tweets to user's keywords

    :param session: session connection
    :param user: logged in user id
    """
    search_input = validate_str("Enter keywords: ", session, session.home)
    s_tweets = TweetSearch(session, user, search_input)
    s_tweets.get_search_tweets()
    return s_tweets 


class Tweet:

    def __init__(self, session, user, data):
        """ Represents a single tweet, helps to display tweets to console
        
        param conn: database session connection 
        param user: logged in user (not the tweet writer)
        param data: row values from tweets table corresponding to columns 
        """
        self.session = session
        self.conn = session.get_conn() 
        self.curs = self.conn.cursor()
        self.user = user

        self.id = data[0]
        self.writer = data[1]
        self.date = data[2]
        self.text = data[3].rstrip()
        self.replyto = data[4]

        if len(data) > 5: 
            self.rt_user = data[5]
        else:
            self.rt_user = None

        if self.replyto:
            self.reply_user = get_user_from_tid(self.curs, self.replyto)
            self.reply_name = get_name(self.curs, self.reply_user)
            self.reply_text = get_text_from_tid(self.curs, self.replyto)

        self.date_str = convert_date(self.date)
        self.rep_cnt = get_rep_cnt(self.curs, self.id)
        self.ret_cnt = get_ret_cnt(self.curs, self.id)
        self.writer_name = get_name(self.curs, self.writer)
        self.terms = []

    def author(self):
        """Return the tweet writer"""
        return self.writer

    def retweeter(self):
        """Return the id of retweeter"""
        return self.rt_user

    def tdate(self):
        """Return the tweet date"""
        return self.date_str

    def tid(self):
        """Return the tweet id"""
        return self.id

    def display(self, index=None, rt_user=None):
        """ Displays basic info on a tweet
        Used for first screen after login or a tweet search
      
        :param index (optional): tweet number (1-5)  
        :param user (optional): user id of the user who retweeted this tweet
        """
        col1_width = 25
        col2_width = BORDER_LEN - col1_width - 1

        if index is not None: 
            tweet_index = "Tweet %d" % (index + 1)
        else:
            tweet_index = "Tweet %d" % (self.id) 

        date_line = "| %s" % (self.date_str)
        user_id = "%d (%s)" % (self.writer, self.writer_name)
        

        if self.replyto is not None:
            rep_str = "@%d (%s)" % (self.reply_user, self.reply_name)
            text_str = "| @%s %s" % (self.reply_user, self.text) 
        else:
            rep_str = " "
            text_str = "| " + self.text

        line1_1 = "{:{width}}".format(tweet_index, width=col1_width)
        line2_1 = "{:{width}}".format(user_id, width=col1_width)
        line3_1 = "{:{width}}".format(rep_str, width=col1_width)
        line1_2 = "{:{width}}".format(date_line, width=col2_width)
        line2_2 = "{:{width}}".format(text_str, width=col2_width)
        line3_2 = "| "

        if rt_user is not None:
            user_name = get_name(self.curs, rt_user)
            retweeted = "| %s Retweeted" % user_name
            line3_2 = line2_2
            line2_2 = line1_2
            line1_2 = "{:{width}}".format(retweeted, width=col2_width)

        print_string(line1_1 + line1_2)
        print_string(line2_1 + line2_2)
        print_string(line3_1 + line3_2)
        print(BORDER)

    def display_stats(self):
        """ Displays statistics on a tweet after a tweet has been selected"""
        print('\n' + BORDER2)
        print_string("Tweet Statistics".upper())
        print(BORDER2)
        print_string("Tweet ID: %d" % (self.id))
        print_string("Written by: %s @%d" % (self.writer_name, self.writer))
        print_string("Posted: %s" % (self.date_str))
        print_string("Text: %s" % (self.text))

        if (self.replyto):
            print_string("Reply to: %s (%s @%d)" % (self.reply_text, self.reply_name, self.reply_user))
        else:
            print_string("Reply to: None")

        print_string("Number of replies: %s" % (self.rep_cnt))
        print_string("Number of retweets: %s" % (self.ret_cnt))

    def reply(self, menu_func):
        """Reply to the Tweet

        :param menu_func: return point if user decides to cancel reply
        """
        compose_tweet(self.session, self.user, menu_func, replyto=self.id)

    def retweet(self):
        """Allows logged in user to retweet a selected tweet"""
        if already_retweeted(self.curs, self.user, self.id):
            print(BORDER)
            print_string("You already retweeted this tweet.")
            print(BORDER)
            return
            
        print(BORDER)
        self.display(rt_user=self.user)
        confirm = validate_yn("Confirm retweet? y/n: ", self.session)
        if confirm in ["n", "no"]:
            print_string("Retweet cancelled.")
        else:
            print(BORDER)
            print_string("Retweeted - %s" % (convert_date(TODAY)))
            data_list = [self.user, self.id, TODAY]
            insert_retweet(self.conn, data_list)
            print(BORDER)

            press_enter()

    def get_values(self):
        """Returns a list of tid, writer, tdate, text, and replyto"""
        return [self.id, self.writer, self.date, self.text, self.replyto]

    def get_terms(self):
        """Returns the list of hashtag terms for the tweet"""
        return self.terms

    def set_terms(self):
        """Finds the hashtags in a tweet and returns the terms""" 
        hashtags = self.find_hashtags() 

        for tag in hashtags:
            term = self.extract_term(tag)
            self.terms.append(term)
        
    def insert_terms(self):
        """Inserts all hashtag terms into the hashtags table"""
        for term in self.terms:
            # Insert into hashtags table
            if not hashtag_exists(self.curs, term):
                insert_hashtag(self.conn, term)      
 
            # Insert into mentions table
            if not mention_exists(self.curs, self.id, term):
                insert_mention(self.conn, [self.id, term])
 
    def valid_terms(self):
        """Returns True if all terms do not exceed restriction length"""
        for term in self.terms:
            if len(term) > 10:
                print_string("%s is too long. Must be 10 characters or less.\n" % (term))
                self.terms = []
                return False
        return True

    def extract_term(self, index):
        """Gets the hashtag term in the tweet based on the index
        
        :param index: the index of the hashtag in the tweet text
        Returns the hashtag term
        """
        space_index = self.text.find(' ', index)
        if space_index < 0:
            space_index = len(self.text) + 1

        return self.text[index+1:space_index]

    def find_hashtags(self):
        """ Returns a list of all indexes of found hashtags"""
        index_list = []
        for i, ch in enumerate(self.text):
            if ch == '#':
                index_list.append(i)
        return index_list

class TweetSearch:

    def __init__(self, session, user, keywords=''):
        """Can be used for getting tweets of users being 
        followed or searching for specific tweets based on keywords
         
        param session: database session connection
        param user: logged in user id
        """ 
        self.session = session
        self.conn = session.get_conn() 
        self.user = user
        self.tweetCurs = self.conn.cursor()
        self.all_tweets = []
        self.tweets = []
        self.more_exist = False
        self.tweet_index = 5
        self.rows = None
        self.searched = keywords
        self.keywords = convert_keywords(keywords)

    def get_searched(self):
        """Returns the user's search input"""
        return self.searched

    def get_search_tweets(self):
        """Find tweets matching keywords"""
        match_tweet(self.tweetCurs, self.keywords, 'tdate')
        self.add_filtered_tweets()
        self.more_tweets()

    def get_user_tweets(self):
        """Find tweets/retweets from users who are being followed"""
        follows_tweets(self.tweetCurs, self.user)
        self.add_tweets()
        self.more_tweets()

    def add_tweets(self):
        """Adds tweets from the query resuls into the all_tweets list"""
        for row in self.tweetCurs.fetchall():
            tweet = Tweet(self.session, self.user, data=row)
            self.all_tweets.append(tweet)

    def add_filtered_tweets(self):
        """Remove tweets from all_tweets list if the tweet does not match
        a keyword
        """
        for row in self.tweetCurs.fetchall():
            tweet = Tweet(self.session, self.user, data=row)
            valid_tweet = True
            if len(self.keywords) > 0:
                valid_tweet = self.validate_tweet(tweet)

            if valid_tweet:
                self.all_tweets.append(tweet)

    def validate_tweet(self, tweet):
        """Returns true if a keyword is not a hashtag and the tweet does not mention it

        :param tweet: Tweet object
        """
        tweet.set_terms()
        for word in self.keywords:
            if not is_hashtag(word) and word in tweet.get_terms():
                return False
        return True

    def more_tweets(self):
        """Gets the next 5 tweets from users who are being followed"""
        assert(self.tweetCurs is not None), 'Unable to select more tweets'

        self.tweets = self.all_tweets[self.tweet_index - 5:self.tweet_index]
        self.more_exist = len(self.all_tweets) - self.tweet_index > 0
        self.tweet_index += 5
  
    def display_tweets(self):
        """Display resulting tweets 5 at a time ordered by date"""
        for i, tweet in enumerate(self.tweets):
            rt_user = tweet.retweeter()
            if rt_user and tweet.author() != rt_user: 
                tweet.display(index=i, rt_user=rt_user)
            else:
                tweet.display(index=i) 

        if len(self.tweets) == 0:
            print_string("You have no tweets yet.")
            print(BORDER + '\n')

    def tweet_menu(self):
        """Displays options to reply or retweet a tweet after it has 
        been selected
        Returns the selected option from the tweet menu
        """
        choices = ["Reply", "Retweet", "Select another tweet", "Home", "Logout"]
        print(BORDER2)
        display_selections(choices)

        return choices

    def select_tweet(self, tweet):
        """Prompt user to choose one of the displayed tweets
        
        Returns selected option from tweet menu 
        """
        choice = 0
        while choice < 4:
            choices = self.tweet_menu()
            choice = validate_num(SELECT, self.session, self.session.home, size=len(choices))

            if choice == 1:
                tweet.reply(self.choose_tweet)
            elif choice == 2:
                tweet.retweet()                    
            elif choice == 3:
                choice = self.choose_tweet()

        if choice == 4:
            self.session.home()
        else:
            self.session.logout()
            
    def choose_tweet(self):
        """Returns the number of the tweet the user wants to select"""
        choices = []
        for i in range(1, len(self.tweets) + 1):
            tweet_str = "Tweet %d" % (i)
            choices.append(tweet_str)

        choices.extend(["Home", "Logout"])
        display_selections(choices, "Tweet Selection")
        choice = validate_num(SELECT, self.session, self.session.home, size=len(choices)) - 1

        if choices[choice] == 'Home':
            self.session.home()
        elif choices[choice] == 'Logout':
            self.session.logout()
        else:
            tweet = self.tweets[choice]
            tweet.display_stats()
            self.select_tweet(tweet)

    def tweets_exist(self):
        """Return true if user has tweets to display"""
        return True if len(self.tweets) > 0 else False

    def more_tweets_exist(self):
        """Return true if more tweets can be displayed"""
        return self.more_exist
