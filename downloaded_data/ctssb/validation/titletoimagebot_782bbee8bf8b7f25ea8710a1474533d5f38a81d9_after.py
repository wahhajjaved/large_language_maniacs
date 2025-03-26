#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Title2ImageBot
Complete redesign of titletoimagebot by gerenook with non-deprecated apis

This file contains the main methods, and the methods to handle post processing
Image Processing / Imgur Uploading is done in t2utils

"""

author = 'calicocatalyst'
version = '0.3b'

import praw
from praw.models import MoreComments, Comment
import pyimgur
from PIL import Image, ImageDraw, ImageFont, ImageSequence

from gfypy import gfycat
import argparse
import messages
import time
import logging
from math import ceil
from os import remove
import re
import requests
from io import BytesIO

import configparser


class TitleToImageBot(object):
    def __init__(self):
        pass
    def check_mentions_for_requests(self, postlimit=10):
        for message in reddit.inbox.all(limit=postlimit):
            self.process_message(message)
    def check_subs_for_posts(self, postlimit=25):
        subs = get_automatic_processing_subs()
        for sub in subs:
            boot = sub == 'boottoobig'
            subr = reddit.subreddit(sub)
            for post in subr.new(limit=postlimit):
                if check_if_parsed(post.id):
                    continue
                title = post.title
                if boot:
                    triggers = [',', ';', 'roses']
                    if not any(t in title.lower() for t in triggers):
                        logging.debug('Title is probably not part of rhyme, skipping submission')
                        add_parsed(post.id)
                        continue
                self.process_submission(post, None, None)
                add_parsed(post.id)
    
    def reply_imgur_url(self, url, submission, source_comment, upscaled=False):
        """
        :param url: Imgur Url
        :type url: str
        :param submission: Submission that the post was on. Reply if source_comment = False
        :type submission: praw.models.Submission
        :param source_comment: Comment that invoked bot if it exists
        :type source_comment: praw.models.Comment
        :returns: True on success, False on failure
        :rtype: bool
        """
        if url == None:
    
            logging.info('URL returned as none.')
            logging.debug('Checking if Bot Has Already Processed Submission')
            # This should return if the bot has already replied.
            # So, lets check if the bot has already been here and reply with that instead!
            for comment in submission.comments.list():
                if isinstance(comment, MoreComments):
                    # See praw docs on MoreComments
                    continue
                if not comment or comment.author == None:
                    # If the comment or comment author was deleted, skip it
                    continue
                if comment.author.name == reddit.user.me().name and 'Image with added title' in comment.body:
                    if source_comment:
                        self.responded_already_reply(source_comment, comment, submission)
    
            add_parsed(submission.id)
            # Bot is being difficult and replying multiple times so lets try this :)
            return
        logging.info('Creating reply')
        reply = messages.standard_reply_template.format(
            image_url=url,
            nsfw="(NSFW)" if submission.over_18 else '',
            upscaled=' (image was upscaled)\n\n' if upscaled else '',
            submission_id=submission.id
        )
        try:
            if source_comment:
                source_comment.reply(reply)
            else:
                submission.reply(reply)
        except praw.exceptions.APIException as error:
            logging.error('Reddit api error, we\'ll try to repost later | %s', error)
            return False
        except Exception as error:
            logging.error('Cannot reply, skipping submission | %s', error)
            return False
        add_parsed(submission.id)
        return True
    
    def responded_already_reply(self, source_comment, comment, submission):
        com_url = messages.comment_url.format(postid=submission.id, commentid=comment.id)
        reply = messages.already_responded_message.format(commentlink=com_url)
        
        source_comment.reply(reply)
        
        add_parsed(source_comment.id)
    
    def process_submission(self, submission, source_comment, title):
        '''
        Process Submission Using t2utils given the above args, and use the other
            provided function to reply
    
        :param submission: Submission object containing image to parse
        :type submission: praw.models.submission
        :param source_comment: Comment that invoked if any did, may be NoneType
        :type source_comment: praw.models.Comment
        :param title: Custom title if any (Currently it will always be None)
        :type title: String
        '''
    
        url = process_image_submission(submission)
        self.reply_imgur_url(url, submission, source_comment)
    
    def process_message(self, message):
        """Process given message (remove, feedback, mark good/bad bot as read)
    
        :param message: the inbox message, comment reply or username mention
        :type message: praw.models.Message, praw.models.Comment
        """
        if not message.author:
            return
        author = message.author.name
        subject = message.subject.lower()
        body_original = message.body
        body = message.body.lower()
        if check_if_parsed(message.id):
            logging.debug("bot.process_message() Message %s Already Parsed, Returning", message.id)
            return
        if message.author.name.lower()=="the-paranoid-android":
            message.reply("Thanks Marv")
            logging.info("Thanking marv")
            add_parsed(message.id)
            return
        # Skip Messages Sent by Bot
        if author == reddit.user.me().name:
            logging.debug('Message was sent, returning')
            return
        # process message
        if (isinstance(message, Comment) and
                (subject == 'username mention' or
                 (subject == 'comment reply' and 'u/title2imagebot' in body))):
            # Dont reply to automod.
            if message.author.name.lower() == 'automoderator':
                message.mark_read()
                return
    
            match = False
            title = None
            if match:
                title = match.group(1)
                if len(title) > 512:
                    title = None
                else:
                    logging.debug('Found custom title: %s', title)
            self.process_submission(message.submission, message, title)
    
            message.mark_read()
        elif subject.startswith('feedback'):
            logging.debug("TODO: add feedback forwarding support")
        # mark short good/bad bot comments as read to keep inbox clean
        elif 'good bot' in body and len(body) < 12:
            logging.debug('Good bot message or comment reply found, marking as read')
            message.mark_read()
        elif 'bad bot' in body and len(body) < 12:
            logging.debug('Bad bot message or comment reply found, marking as read')
            message.mark_read()
        add_parsed(message.id)
        
    def run(self, limit):
        logging.info('Checking Mentions')
        self.check_mentions_for_requests(limit)
        logging.info('Checking Autoreply Subs')
        self.check_subs_for_posts(limit)




class RedditImage:
    """RedditImage class

    :param image: the image
    :type image: PIL.Image.Image
    """
    margin = 10
    min_size = 500
    # TODO find a font for all unicode chars & emojis
    # font_file = 'seguiemj.ttf'
    font_file = 'roboto-emoji.ttf'
    font_scale_factor = 16
    # Regex to remove resolution tag styled as such: '[1000 x 1000]'
    regex_resolution = re.compile(r'\s?\[[0-9]+\s?[xX*×]\s?[0-9]+\]')

    def __init__(self, image):
        self._image = image
        self.upscaled = False
        width, height = image.size
        # upscale small images
        if image.size < (self.min_size, self.min_size):
            if width < height:
                factor = self.min_size / width
            else:
                factor = self.min_size / height
            self._image = self._image.resize((ceil(width * factor),
                                              ceil(height * factor)),
                                             Image.LANCZOS)
            self.upscaled = True
        self._width, self._height = self._image.size
        self._font_title = ImageFont.truetype(
            self.font_file,
            self._width // self.font_scale_factor
        )

    def _split_title(self, title):
        """Split title on [',', ';', '.'] into multiple lines

        :param title: the title to split
        :type title: str
        :returns: split title
        :rtype: list[str]
        """
        lines = ['']
        all_delimiters = [',', ';', '.']
        delimiter = None
        for character in title:
            # don't draw ' ' on a new line
            if character == ' ' and not lines[-1]:
                continue
            # add character to current line
            lines[-1] += character
            # find delimiter
            if not delimiter:
                if character in all_delimiters:
                    delimiter = character
            # end of line
            if character == delimiter:
                lines.append('')
        # if a line is too long, wrap title instead
        for line in lines:
            if self._font_title.getsize(line)[0] + RedditImage.margin > self._width:
                return self._wrap_title(title)
        # remove empty lines (if delimiter is last character)
        return [line for line in lines if line]

    def _wrap_title(self, title):
        """Wrap title

        :param title: the title to wrap
        :type title: str
        :returns: wrapped title
        :rtype: list
        """
        lines = ['']
        line_words = []
        words = title.split()
        for word in words:
            line_words.append(word)
            lines[-1] = ' '.join(line_words)
            if self._font_title.getsize(lines[-1])[0] + RedditImage.margin > self._width:
                lines[-1] = lines[-1][:-len(word)].strip()
                lines.append(word)
                line_words = [word]
        # remove empty lines
        return [line for line in lines if line]

    def add_title(self, title, boot, bg_color='#fff', text_color='#000'):
        """Add title to new whitespace on image

        :param title: the title to add
        :type title: str
        :param boot: if True, split title on [',', ';', '.'], else wrap text
        :type boot: bool
        """
        beta_centering = False
        # remove resolution appended to title (e.g. '<title> [1000 x 1000]')
        title = RedditImage.regex_resolution.sub('', title)
        line_height = self._font_title.getsize(title)[1] + RedditImage.margin
        lines = self._split_title(title) if boot else self._wrap_title(title)
        whitespace_height = (line_height * len(lines)) + RedditImage.margin
        new = Image.new('RGB', (self._width, self._height + whitespace_height), bg_color)
        new.paste(self._image, (0, whitespace_height))
        draw = ImageDraw.Draw(new)
        for i, line in enumerate(lines):
            w,h = self._font_title.getsize(line)
            left_margin = ((self._width - w)/2) if beta_centering else RedditImage.margin
            draw.text((left_margin, i * line_height + RedditImage.margin),
                      line, text_color, self._font_title)
        self._width, self._height = new.size
        self._image = new

    def upload(self, imgur):
        """Upload self._image to imgur

        :param imgur: the imgur api client
        :type imgur: imgurpython.client.ImgurClient
        :param config: imgur image config
        :type config: dict
        :returns: imgur url if upload successful, else None
        :rtype: str, NoneType
        """
        path_png = 'temp.png'
        path_jpg = 'temp.jpg'
        self._image.save(path_png)
        self._image.save(path_jpg)
        try:
            response = imgur.upload_image(path_png, title="Uploaded by /u/Title2ImageBot")
        except:
            # Likely too large
            logging.warning('png upload failed, trying jpg')
            try:
                response = imgur.upload_image(path_jpg, title="Uploaded by /u/Title2ImageBot")
            except:
                logging.error('jpg upload failed, returning')
                return None
        finally:
            remove(path_png)
            remove(path_jpg)
        return response.link

# -- UTILS --

def check_config_for_sub_threshold(sub, config_file="config.ini"):
    config = configparser.ConfigParser()
    config.read(config_file)
    if config.has_option(sub, 'threshold'):
        return int(config[sub]['threshold'])
    else:
        return -1

def get_automatic_processing_subs(config_file="config.ini"):
    config = configparser.ConfigParser()
    config.read(config_file)
    sections = config.sections()
    sections.remove('RedditAuth')
    sections.remove('ImgurAuth')
    sections.remove('GfyCatAuth')
    return sections


def process_image_submission(submission, commenter=None, customargs=None):
    # TODO implement user selectable options on summons

    # Make sure author account exists
    if not submission.author:
        add_parsed(submission.id)
        return None;

    sub = submission.subreddit.display_name
    url = submission.url
    title = submission.title
    author = submission.author.name

    # We need to verify everything is good to go
    # Check every item in this list and verify it is 'True'
    # If the submission has been parsed, throw false which will not allow the Bot
    #   To post.
    not_parsed = not check_if_parsed(submission.id)
    # TODO add gif support

    checks = [not_parsed]

    if not all(checks):
        print("Checks failed, not submitting")
        return;


    if  url.endswith('.gif') or url.endswith('.gifv'):
        # Lets try this again.
        try:
            return process_gif(submission)
        except:
            logging.warn("gif upload failed")
            return None
    # Attempt to grab the images
    try:
        response = requests.get(url)
        img = Image.open(BytesIO(response.content))
    except OSError as error:
        logging.warning('Converting to image failed, trying with <url>.jpg | %s', error)
        try:
            response = requests.get(url + '.jpg')
            img = Image.open(BytesIO(response.content))
        except OSError as error:
            logging.error('Converting to image failed, skipping submission | %s', error)
            return
    except IOError as error:
        print('Pillow couldn\'t process image, marking as parsed and skipping')
        return None;
    except Exception as error:
        print(error)
        print('Exception on image conversion lines.')
        return None;
    try:
        image = RedditImage(img)
    except Exception as error:
        # TODO add error in debug line
        print('Could not create RedditImage with error')
        return None;
    image.add_title(title, False)

    imgur = get_imgur_client_config()
    imgur_url = image.upload(imgur)

    return imgur_url

def process_gif(submission):
    sub = submission.subreddit.display_name
    url = submission.url
    title = submission.title
    author = submission.author.name
 
    # If its a gifv and hosted on imgur, we're ok, anywhere else I cant verify it works
    if 'imgur' in url and url.endswith("gifv"):
        # imgur will give us a (however large) gif if we ask for it
        # thanks imgur <3
        url = url.rstrip('v')
    # Reddit Hosted gifs are going to be absolute hell, served via DASH which
    #       Can be checked through a fallback url :)
    try:
        response = requests.get(url)
    # Try to get an image if someone linked to imgur but didn't put the .file ext.
    except OSError as error:
        logging.warning('Converting to image failed, trying with <url>.jpg | %s', error)
        try:
            response = requests.get(url + '.jpg')
            img = Image.open(BytesIO(response.content))
        # If that wasn't the case
        except OSError as error:
            logging.error('Converting to image failed, skipping submission | %s', error)
            return
    # Lord knows
    except IOError as error:
        print('Pillow couldn\'t process image, marking as parsed and skipping')
        return None;
    # The nature of this throws tons of exceptions based on what users throw at the bot
    except Exception as error:
        print(error)
        print('Exception on image conversion lines.')
        return None;
    except:
        logging.error("Could not get image from url")
        return None;
 
    img = Image.open(BytesIO(response.content))
    frames = []
 
    # Process Gif
 
    # Loop over each frame in the animated image
    for frame in ImageSequence.Iterator(img):
        # Draw the text on the frame
 
        # We'll create a custom RedditImage for each frame to avoid
        #      redundant code
 
        # TODO: Consolidate this entire method into RedditImage. I want to make
        #       Sure this works before I integrate.
 
        rFrame = RedditImage(frame)
        rFrame.add_title(title, False)
 
        frame = rFrame._image
        # However, 'frame' is still the animated image with many frames
        # It has simply been seeked to a later frame
        # For our list of frames, we only want the current frame
 
        # Saving the image without 'save_all' will turn it into a single frame image, and we can then re-open it
        # To be efficient, we will save it to a stream, rather than to file
        b = BytesIO()
        frame.save(b, format="GIF")
        frame = Image.open(b)
 
        # The first successful image generation was 150MB, so lets see what all
        #       Can be done to not have that happen
 
        # Then append the single frame image to a list of frames
        frames.append(frame)
    # Save the frames as a new image
    path_gif = 'temp.gif'
    path_mp4 = 'temp.mp4'
    frames[0].save(path_gif, save_all=True, append_images=frames[1:])
    # ff = ffmpy.FFmpeg(inputs={path_gif: None},outputs={path_mp4: None})
    # ff.run()
 
    try:
        url = get_gfycat_client_config().upload_file(path_gif).url
        remove(path_gif)
    except:
        logging.error('Gif Upload Failed, Returning')
        remove(path_gif)
        return None
    # remove(path_mp4)
    return url

def get_gfycat_client_config(config_file="config.ini"):
    config = configparser.ConfigParser()
    config.read(config_file)
    client_id = config['GfyCatAuth']['publicKey']
    client_secret = config['GfyCatAuth']['privateKey']
    username = config['GfyCatAuth']['username']
    password = config['GfyCatAuth']['password']
    client = gfycat.GfyCatClient(client_id,client_secret,username,password)
    return client

def auth_reddit_from_config(config_file='config.ini'):
    config = configparser.ConfigParser()
    config.read(config_file)
    return(praw.Reddit(client_id=config['RedditAuth']['publicKey'],
        client_secret=config['RedditAuth']['privateKey'],
        username=config['RedditAuth']['username'],
        password=config['RedditAuth']['password'],
        user_agent=config['RedditAuth']['userAgent']))


reddit = auth_reddit_from_config()

def get_imgur_client_config(config_file="config.ini"):
    config = configparser.ConfigParser()
    config.read(config_file)
    return(pyimgur.Imgur(config['ImgurAuth']['publicKey']))


comment_file_path = "parsed.txt"

def add_parsed(id):
    with open(comment_file_path, 'a+') as f:
        f.write(id)

def check_if_parsed(id):
    with open(comment_file_path,'r+') as f:
        return id in f.read();

def main():
    parser = argparse.ArgumentParser(description='Bot To Add Titles To Images')
    parser.add_argument('-d', '--debug', help='Enable Debug Logging', action='store_true')
    parser.add_argument('-l', '--loop', help='Enable Looping Function', action='store_true')
    parser.add_argument('limit', help='amount of submissions/messages to process each cycle',
                        type=int)
    parser.add_argument('interval', help='time (in seconds) to wait between cycles', type=int)

    args = parser.parse_args()
    if args.debug:
        logging.basicConfig(format='%(asctime)s - %(message)s', datefmt='%d-%b-%y %H:%M:%S', level=logging.DEBUG);
    else:
        logging.basicConfig(format='%(asctime)s - %(message)s', datefmt='%d-%b-%y %H:%M:%S', level=logging.INFO);

    # logging.info('Bot initialized, processing the last %s submissions/messages every %s seconds' % (args.limit, args.interval))
    bot = TitleToImageBot()
    
    
    logging.debug('Debug Enabled')
    if not args.loop:
        bot.run(args.limit)
        logging.info('Checking Complete, Exiting Program')
        exit(0)
    while True:
        bot.run(args.limit)
        logging.info('Checking Complete')
        time.sleep(args.interval)



if __name__ == '__main__':
    main()
