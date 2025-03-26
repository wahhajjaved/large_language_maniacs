#!/usr/bin/python
import sys
import os
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

def convert_directory_to_markdown(input_path):
    if (os.path.isdir(input_path)):
        print('Processing directory ' + input_path)
        files = [f for f in os.listdir(input_path) if os.path.isfile(os.path.join(input_path, f))]
        
        for file in files:
            file_path = os.path.join(input_path, file)
            filename, file_extension = os.path.splitext(file_path)
            if file_extension.upper() == '.HTML':                
                file_markdown = filename + '.md'
                convert_html_to_markdown(file_path, file_markdown)

def main():
    if (len(sys.argv) == 3):
        convert_html_to_markdown(sys.argv[1], sys.argv[2])
    elif (len(sys.argv) == 2):
        convert_directory_to_markdown(sys.argv[1])
    else:
        print('Usage: \npython main.py path_to_html_file path_to_output_markdown')
        print('or ... python main.py directory_to_convert')
        

if __name__ == "__main__":
    main()