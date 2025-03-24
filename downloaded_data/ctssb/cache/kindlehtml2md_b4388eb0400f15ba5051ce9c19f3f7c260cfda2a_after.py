#!/usr/bin/python
import sys
import codecs
import urllib
from bs4 import BeautifulSoup

PATH = './examples/How_to_study.html'

def convert_html_to_markdown(input_path, output_path):
    print('Processing file ' + input_path + ' to generate ' + output_path)
    soup = BeautifulSoup(open(input_path), 'html.parser')

    f = codecs.open(output_path, 'w', 'utf-8')
    
    divs = soup.findAll('div', {'class': ['bookTitle', 'sectionHeading', 'noteText']})
    for div in divs:
        if (div['class'][0] == 'bookTitle'):
            f.write('# ' + div.text.strip() + '\n')
        elif (div['class'][0] == 'sectionHeading'):
            f.write('## ' + div.text.strip() + '\n')
        elif (div['class'][0] == 'noteText'):
            f.write(div.text.strip() + '\n')

    f.close()

def main():
    if len(sys.argv) != 3:
        print('Usage: python main.py path_to_html_file path_to_output_markdown')
    else:
        convert_html_to_markdown(sys.argv[1], sys.argv[2])

if __name__ == "__main__":
    main()