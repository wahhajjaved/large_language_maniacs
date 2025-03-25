#######
## Bibdoc Wikifier
## This takes a file containing json'd bib-docs, and produces a table from bibcode to a list of top titles for that bibcode.
## @author jmilbauer, jdhanoa for Hopper Project @ UChicago
#######

import pickle
import ahocorasick
import sys, os
import json
import shutil
from core.funcs import *
import re
import argparse

globalcount = 0

def remove_latex(text):
    text = clean_inline_math(text)
    for match in grab_inline_math(text):
        text = text.replace(match, "")
    text = re.sub(non_capture_math, '', text)
    text = re.sub(r'\\begin\{title\}(.+?)\\end\{title\}',r'\1',text)
    text = re.sub(r'(?s)\\begin\{picture\}.+?\\end\{picture\}','',text)
    text = re.sub(r'\\def.+','',text)
    text = re.sub(r'\\section\*?\{(.+?)\}',r'\1',text)
    text = re.sub(r'\\def.+|\\\@ifundefined.+|(?s)\\begin\{thebibliography\}.+?\\end\{thebibliography\}|(?s)\\begin\{eqnarray\*?\}.+?\\end\{eqnarray\*?\}|\\[\w@]+(?:\[.+?\])?(?:\{.+?\})*|\[.+?\](?:\{.+?\})?|\{cm\}','',text)
    text = re.sub(r'\}','',text)
    text = re.sub(r'\{','',text)
    text = re.sub(r'\(\)','',text)
    text = re.sub(r'\}','',text)
    text = re.sub(r'\\','',text)
    text = re.sub(r'\n{3,}','',text)
    return text

def stderr(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)

def find_anchors_tex(file_path):
    global topranks
    global keywords
    global automaton
    ahc_automaton = automaton
    topranks = keywords

    if not file_path.endswith('.tex'):
        return
    with open(file_path,'r', encoding='latin-1') as fh:
        text = fh.read()
    haystack = remove_latex(grab_body(text))
    article_anchors = {} # {anchor : freq}
    for end_index, (anchor, title) in ahc_automaton.iter(haystack):
        start_index = end_index-len(anchor)+1
        if anchor in article_anchors.keys():
            article_anchors[anchor] += 1
        else:
            article_anchors[anchor] = 1
        assert haystack[start_index:start_index + len(anchor)] == anchor
        assert title == topranks[anchor][0]
    folder, fname = os.path.split(file_path)
    output_path = os.path.join(output_path, fname)+os.path.splitext(os.path.basename(file_path))+'.tsv'
    with open(output_path, 'w') as fh:
        for anchor in article_anchors.keys():
            fh.write("{}\t{}\t{}\t{}".format(bibcode, anchor,
            article_anchors[anchor], topranks[anchor][1]))


def find_anchors(json_file_path, output_path, anchor_list, topranks,
                                                     ahc_automaton):
    if not json_file_path.endswith('.json'):
        return
    filename = os.path.basename(json_file_path)
    #os.path .up().down().enter("...")
    output_file_path = output_path + filename + '.a-t.tsv'
    jsons = []
    path_anchors = []
    with open(json_file_path, 'r') as fp:
        for line in fp:
            jsons += (json.loads(line))
#    print(len(jsons))

    #good up to here

    fp = open(output_file_path, 'w')
    #fp.close()
    # fp = open(output_file_path, 'a')
    js_counter = 0
    for article in jsons:
        global globalcount
        js_counter += 1
        globalcount += 1
        if (globalcount % 5000 == 0):
            print("{} bibdocs processed.".format(globalcount))

        bibcode = article["bibcode"]
        if "body" not in article.keys():
            fp.write("{}\tnone\tnone\tnone\tnone".format(bibcode))
            continue #do not execute following code in loop.

        abstract = article["abstract"]
        body = article["body"]

        haystack = body.encode('utf8', 'ignore') #convert the unicode from json into ascii so pyahocorasick can read it

        article_anchors = {} #{anchor : freq}

        for end_index,(anchor,title) in ahc_automaton.iter(haystack):
            start_index = end_index - len(anchor) + 1
            if anchor in article_anchors.keys():
                article_anchors[anchor] += 1
            else:
                article_anchors[anchor] = 1
            assert haystack[start_index:start_index + len(anchor)] == anchor
            assert title == topranks[anchor][0]

        for anchor in article_anchors.keys():
            fp.write("{}\t{}\t{}\t{}\t{}".format(bibcode, anchor, article_anchors[anchor], topranks[anchor][0], topranks[anchor][1]))

    #print("{} jsons".format(js_counter))
    fp.close()

def pad_keyword(string):
    return " " + string + " "

def main():
    global topranks
    global automaton
    global keywords

    parser = argparse.ArgumentParser(
    description='''Takes a file containing json\'d bib docs and returns a list
    of top titles. One of either the --json or --tex flags must be specified'''
    )
    parser.add_argument('data_path',
    help='Directory containing data.p and ranks.p from extractor')
    parser.add_argument('input_path',
    help='Directory containing articles')
    parser.add_argument('output_path',
    help='The output path should be where you want a document containing the json\'d extracted titles to be stored')

    parser.add_argument('--json', action='store_true',
    help='Specifies if the input is a JSON of articles')
    parser.add_argument('--tex', action='store_true',
    help='Specifies if the input is a folder of .tex files',)
    args = parser.parse_args()
    input_path = args.input_path
    output_path = args.output_path
    data_path = args.data_path

    rank_path = os.path.join(data_path, 'topranks.tsv')
    topranks = {}
    with open(rank_path, 'r') as fp:
        for line in fp:
            contents = line.split('\t')
            if len(contents) == 3:
                anchor = pad_keyword(contents[0])
                title = contents[1]
                freq = contents[2]
                topranks[anchor] = (title, freq)

    keywords = topranks.keys()
    automaton = ahocorasick.Automaton()
    for key in keywords:
        automaton.add_word(key, (key, topranks[key][0])) #keep in mind for mem reduction
    automaton.make_automaton()



    if args.tex:
        shutil.copytree(input_path, output_path)
        flist = []
        for root, folders, files in os.walk(output_path):
            for fname in files:
                if fname.endswith('.tex'):
                    flist.append(os.path.join(root, fname))
        pool = mp.Pool(mp.cpu_count())
        pool.map(flist, find_anchors_tex)
        pool.close()
        pool.join()
    elif args.json:
        allfiles = os.listdir(input_path)
        allpaths = map(lambda x: os.path.join(input_path, x), allfiles)
        bibcode_map = {} #{bibcode : [(title, freq)]}

            #freq will represent the TOTAL occurences of an anchor that mapped to the appropriate title

        fp2 = open('bibdoc_wikifier_log.txt', 'w')
        for path in allpaths:
            fp2.write("About to process {}".format(path))
            find_anchors(path, output_path, keywords, topranks, automaton)
            fp2.write("\tCompleted {}\n".format(path))
        fp2.close()
        #     all_anchors += path_anchors
        #
        # result = {}
        # for anchor in all_anchors:
        #     title = topranks[anchor][0]
        #     print("Found: {}, Incrementing: {}".format(anchor, title))
        #     if title in result.keys():
        #         result[title] += 1
        #     else:
        #         result[title] = 1
        sys.exit(0)
    else:
        stderr("Error: Must choose either tex or json flag")
        sys.exit(1)


if sys.flags.interactive:
    pass
else:
    if __name__=='__main__':
        main()
