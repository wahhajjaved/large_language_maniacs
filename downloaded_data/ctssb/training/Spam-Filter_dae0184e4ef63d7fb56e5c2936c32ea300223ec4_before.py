import email.parser
from os import listdir
from os.path import isfile, join
import string
import BeautifulSoup
import re


def visible(element):
    if element.parent.name in ['style', 'script', '[document]', 'head', 'title']:
        return False
    elif re.match('<!--.*-->', str(element)):
        return False
    return True


class Parser:
    prsr = None

    def __init__(self):
        self.prsr = email.parser.Parser()

    def parse(self, folder_path):
        current_files = [f for f in listdir(folder_path) if isfile(join(folder_path, f))]
        email_texts = []
        results = []
        for email_file in current_files:
            with open(folder_path + email_file, 'r') as fp:
                results.append(self.prsr.parse(fp))
        while len(results)>0:
            result = results.pop()
            ctype = result.get_content_type()
            current_message = ""
            if result.is_multipart():
                for parts in result.walk():
                    if not parts.is_multipart():
                        results.append(parts)
            elif "html" in ctype:
                current_message = result.get_payload()
                soup = BeautifulSoup.BeautifulSoup(current_message)
                texts = soup.findAll(text=True)
                visible_texts = filter(visible, texts)
                string_texts = "".join([c.encode("UTF-8") for c in visible_texts])
                email_texts.append(re.sub("[ ]+", " ", re.sub("[^a-zA-Z0-9]", " ", string_texts)))
            elif "plain" in ctype:
                email_texts.append(result.get_payload())
            #else:
            #    print ctype
        return email_texts
