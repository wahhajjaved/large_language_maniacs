# -*- coding: utf-8 -*-


"""gitcher prof class

This class represent a gitcher profile instance.
"""

# Authorship
__author__ = 'Borja González Seoane'
__copyright__ = 'Copyright 2019, Borja González Seoane'
__credits__ = 'Borja González Seoane'
__license__ = 'LICENSE'
__version__ = '0.1a1'
__maintainer__ = 'Borja González Seoane'
__email__ = 'dev@glezseoane.com'
__status__ = 'Development'


class Prof(object):
    """Class that represents a gitcher profile."""

    def __init__(self, profname: str, name: str, email: str,
                 signkey: str = None, signpref: bool = False):
        self.profname = profname
        self.name = name
        self.email = email
        self.signkey = signkey
        self.signpref = signpref

    def __str__(self):
        if self.signpref is not None:
            signkey_str = self.signkey
            if self.signpref:
                signpref_str = "Autosign enabled"
            else:
                signpref_str = "Autosign disabled"
        else:
            signkey_str = "GPG Key disabled"
            signpref_str = ""

        return "{0} {1} {2} {3}".format(self.name, self.email, signkey_str,
                                        signpref_str)
