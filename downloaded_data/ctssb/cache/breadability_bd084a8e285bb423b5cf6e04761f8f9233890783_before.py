# -*- coding: utf8 -*-

"""
A fast python port of arc90's readability tool

Usage:
    readability [options] <resource>
    readability --version
    readability --help

Arguments:
  <resource>      URL or file path to process in readable form.

Options:
  -f, --fragment  Output html fragment by default.
  -b, --browser   Open the parsed content in your web browser.
  -d, --debug     Output the detailed scoring information for debugging
                  parsing.
  -v, --verbose   Increase logging verbosity to DEBUG.
  --version       Display program's version number and exit.
  -h, --help      Display this help message and exit.
"""

from __future__ import absolute_import
from __future__ import division, print_function, unicode_literals


import logging
import locale
import urllib
import webbrowser

from tempfile import NamedTemporaryFile
from docopt import docopt
from .. import __version__
from ..readable import Article


def parse_args():
    return docopt(__doc__, version=__version__)


def main():
    args = parse_args()
    logger = logging.getLogger("readability")

    if args["--verbose"]:
        logger.setLevel(logging.DEBUG)

    resource = args["<resource>"]
    if resource.startswith("www"):
        resource = "http://" + resource

    url = None
    if resource.startswith("http://") or resource.startswith("https://"):
        url = resource

        response = urllib.urlopen(url)
        content = response.read()
        response.close()
    else:
        with open(resource, "r") as file:
            content = file.read()

    document = Article(content, url=url, fragment=args["--fragment"])
    if args["--browser"]:
        html_file = NamedTemporaryFile(mode="w", suffix=".html", delete=False)

        content = document.readable.encode("utf8")
        html_file.write(content)

        webbrowser.open(html_file.name)

        html_file.close()
    else:
        encoding = locale.getpreferredencoding()
        content = document.readable.encode(encoding)
        print(content)


if __name__ == '__main__':
    main()
