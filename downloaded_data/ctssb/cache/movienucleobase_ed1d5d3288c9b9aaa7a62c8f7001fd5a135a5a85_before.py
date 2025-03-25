"""
.. module:: datastructures
    :synopsis: A module that provides the data structures to store movie data

.. moduleauthor:: Pedro Araujo <pedroaraujo@colorlesscube.com>
.. moduleauthor:: Pedro Nogueira <pedro.fig.nogueira@gmail.com>
"""

import logging
import itertools


class MovieData:
    """This class contains all information related to the movie being analyzed.

    This class stores mostly characters and scenes and it provides a number of
    methods to access to these attributes.

    Attributes:
        title (str): Movie title
        sub_wikia (str): Sub-wikia related to the movie. Used for completing
        information about the movies' characters
        characters (list of MovieCharacter): List of all characters in the movie
        scenes (list of str): List of all scenes from the movie
    """

    def __init__(self, title, sub_wikia):
        """This function initializes the movie information.
        
        Args:
            title (String): Movie title
            sub_wikia (String): The sub-wikia related to the movie

        Returns:
            None
        """

        self._title = title
        self._sub_wikia = sub_wikia

    @property
    def title(self):
        return self._title 

    @property
    def sub_wikia(self):
        return self._sub_wikia

    @property
    def characters(self):
        """Return the movie characters
        
        Returns:
            List of MovieCharacter: Movie characters
        """

        return self._characters

    @characters.setter
    def characters(self, x):
        """Set the characters.
        
        Args:
             x (list of MovieCharacter): List of characters extracted
            from the movie script
        """

        self._characters = x

    @property
    def scenes(self):
        """Return the movie scenes
        
        Returns:
            List of string: Movie scenes
        """

        return self._scenes

    @scenes.setter
    def scenes(self, x):
        """Set the movie scenes.
        
        Args:
            x (list of str): List of all scenes from the movie
        """

        self._scenes = x

    def print_info(self):
        """Print the movie information:
            - Movie title
            - Sub-wikia
            - All of the characters' names
        """

        print 'Title of the movie:'
        print '    - ' + self.title
        print 'Sub-wikia:'
        print '    - ' + self.sub_wikia

        self.print_characters()

    def print_characters(self):
        """List the movie characters' names:
            - Movie script names
            - Real names
        """

        print 'Characters of the movie:'

        for character in self.characters:
            print '    - Name: ' + character.name + \
                  ' ; Real name: ' + character.real_name + \
                  ' ; Gender: ' + character.gender

    def clean_up_character_list(self):
        real_name_list = []

        for character in self.characters:
            if character.real_name not in real_name_list:
                real_name_list.append(character.real_name)
            else:
                self.characters.remove(character)

class MovieCharacter:
    def __init__(self, name):
        self._id = id
        self._name = name
        self._real_name = ""
        self._gender = ""
        self._characters_interacted_with = {}
        self._mentioned_characters = {}
        self._appeared_scenes = []

    @property
    def id(self):
        return self._id

    @property
    def name(self):
        return self._name

    @property
    def real_name(self):
        return self._real_name

    @property
    def gender(self):
        return self._gender

    @property
    def appeared_scenes(self):
        return self._appeared_scenes

    @property
    def characters_interacted_with(self):
        return self._characters_interacted_with

    @property
    def mentioned_characters(self):
        return self._mentioned_characters

    @real_name.setter
    def real_name(self, x):
        self._real_name = x

    @gender.setter
    def gender(self, x):
        self._gender = x

    def add_characters_interacted_with(self, list_of_names,char_list):
        # The function will accept a list of characters that the present
        # character interacted during a scene.
        #
        # It is desirable to add all of these characters to the list but
        # the list will also contain the present character as well. So we
        # need to make sure to exclude it from the list.
        #
        # But it is also possible that the character speaks with himself
        # in the whole scene. This scenario also counts as well, so we
        # only add the character if it is the only element in the list.
        logger = logging.getLogger(__name__)

        added_character = ""

        # If the lists of names is empty, terminate the function immediately
        if len(list_of_names)==0:
            return False

        # Detect which characters were already added as interactions and
        # increase the respective counters of interactions
        for l in set(list_of_names).intersection(self._characters_interacted_with):
            if l in self._characters_interacted_with and l!=self.name:
                added_character = l
                self._characters_interacted_with[l] = self._characters_interacted_with[l] + 1

        # Detect the characters that weren't added as interaction yet
        for l in set(list_of_names).difference(self._characters_interacted_with):
            if l in char_list and l!=self.name:
                added_character = l
                self._characters_interacted_with[l] = 1

        logger.debug('The character ' + self.name + ' interacted with: ' + l)

        return True

    def add_appeared_scene(self, scene_number):
        logger = logging.getLogger(__name__)

        logger.debug('The character ' + self.name + 
                     ' appears in the scene ' + str(scene_number))

        try:
            self._appeared_scenes.append(scene_number)
        except NameError:
            self._appeared_scenes = [scene_number]

    def add_mentioned_character(self, name):
        logger = logging.getLogger(__name__)

        if name in self.mentioned_characters:
            self._mentioned_characters[name] = \
                self._mentioned_characters[name] + 1
        else:
            self._mentioned_characters[name] = 1

        logger.debug('The character ' + self.name + ' mentioned ' + name)

    def list_characters_interacted_with(self):
        if len(self._characters_interacted_with)>0:
            print 'The character ' + self.name + ' interacted with:'

            for char in self._characters_interacted_with:
                print '    - ' + char + ' ' + \
                    str(self.characters_interacted_with[char]) + ' times'
        else:
            print 'The character ' + self.name + ' did\'t have any interactions'

    def list_mentioned_characters(self):
        if len(self.mentioned_characters):
            print 'The character ' + self.name + ' mentioned the following characters:'

            for char in self.mentioned_characters:
                print '    - ' + char + ' ' + \
                    str(self.mentioned_characters[char]) + ' times'
        else:
            print 'The character did not mentioned anyone.'

    def list_appeared_scenes(self):
        if self.appeared_scenes:
            print 'The character ' + self.name + ' appeared in the following scenes: ' + \
                ', '.join(str(i) for i in self.appeared_scenes)
        else:
            print 'The character did not appear in any scenes.'




