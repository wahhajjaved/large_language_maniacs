# -*- coding: utf-8 -*-
""" collective.recipe.htpasswd
"""

import crypt
import logging
import os
import random
import string

import zc.buildout


class Recipe(object):
    """ This recipe should not be used to update an existing htpasswd file
        because it overwritte the htpasswd file in every update.
    """

    def __init__(self, buildout, name, options):
        self.buildout = buildout
        self.name = name
        self.options = options
        self.logger = logging.getLogger(self.name)

        supported_algorithms = ('crypt', 'plain')
        if 'algorithm' in options:
            if options['algorithm'].lower() not in supported_algorithms:
                raise zc.buildout.UserError("Currently the only supported "
                                            "method are 'crypt' and 'plain'.")
            else:
                self.algorithm = options['algorithm'].lower()
        else:
            self.algorithm = 'crypt'

        if 'output' not in options:
            raise zc.buildout.UserError('No output file specified.')
        elif os.path.isdir(options['output']):
            raise zc.buildout.UserError('The output file specified is an '
                                        'existing directory.')
        elif os.path.isfile(options['output']):
            self.logger.warning('The output file specified exist and is going '
                                'to be overwritten.')

        self.output = options['output']

        if 'credentials' not in options:
            raise zc.buildout.UserError('You must specified at lest one pair '
                                        'of credentials.')
        else:
            self.credentials = []
            for credentials in options['credentials'].split('\n'):
                if not credentials:
                    continue
                try:
                    (username, password) = credentials.split(':', 1)
                except ValueError:
                    raise zc.buildout.UserError('Every pair credentials must '
                                                'be separated be a colon.')
                else:
                    self.credentials.append((username, password))

            if not self.credentials:
                raise zc.buildout.UserError('You must specified at lest one '
                                            'pair of credentials.')

        if 'mode' in options:
            self.mode = int(options['mode'], 8)
        else:
            self.mode = None

    def install(self):
        """ Create the htpasswd file.
        """
        self.mkdir(os.path.dirname(self.output))
        with open(self.output, 'w+') as pwfile:
            for (username, password) in self.credentials:
                pwfile.write("%s:%s\n" % (username, self.mkhash(password)))

        if self.mode is not None:
            os.chmod(self.output, self.mode)

        self.options.created(self.output)
        return self.options.created()

    def update(self):
        """ Every time that the update method is called the htpasswd file is
            overrided.
        """
        return self.install()

    def mkdir(self, path):
        """ Create the path of directories recursively.
        """
        parent = os.path.dirname(path)
        if not os.path.exists(path) and parent != path:
            self.mkdir(parent)
            os.mkdir(path)
            self.options.created(path)

    def salt(self):
        """ Returns a two-character string chosen from the set [a–zA–Z0–9./].
        """
        #FIXME: This method only works for the salt requiered for the crypt
        # algorithm.
        characters = string.ascii_letters + string.digits + './'
        return random.choice(characters) + random.choice(characters)

    def mkhash(self, password):
        """ Returns a the hashed password as a string.
        """
        # TODO: Add support for MD5 and SHA1 algorithms.
        if self.algorithm == 'crypt':
            if len(password) > 8:
                self.logger.warning((
                    'Only the first 8 characters of the password are '
                    'used to form the password. The extra characters '
                    'will be discarded.'))
            return crypt.crypt(password, self.salt())
        elif self.algorithm == 'md5':
            raise NotImplementedError(
                'The MD5 algorithm has not been implemented yet.')
        elif self.algorithm == 'plain':
            return password
        elif self.algorithm == 'sha1':
            raise NotImplementedError(
                'The SHA1 algorithm has not been implemented yet.')
        else:
            raise ValueError(
                "The algorithm '%s' is not supported." % self.algorithm)
