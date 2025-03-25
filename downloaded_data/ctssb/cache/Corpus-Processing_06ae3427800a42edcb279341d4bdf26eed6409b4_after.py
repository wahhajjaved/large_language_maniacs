__author__ = 'AmirPouya'
from lxml import etree as ET
import time
import io
import re


def write(source_dic,target_dic,output_file,config):
    root=ET.Element('corpus')
    root.attrib['title']=config['corpus_name']
    root.attrib['source_lang']=config['source_lang']
    root.attrib['target_lang']=config['target_lang']
    root.attrib['create_date']=time.strftime("%d/%m/%Y")
    par_id = 1
    source_word_count=0
    target_word_count=0
    for key in sorted(source_dic.keys()):
        if target_dic.has_key(key):
            for seg_key in sorted(source_dic[key].keys()):
                if target_dic[key].has_key(seg_key):
                    par = ET.SubElement(root, 'p')
                    par.attrib['id'] = str(par_id)
                    par_id += 1
                    source=source_dic[key][seg_key].strip()
                    target=target_dic[key][seg_key].strip()
                    src = ET.SubElement(par, 'source')
                    src.text = source_dic[key][seg_key].strip()
                    trg = ET.SubElement(par, 'target')
                    trg.text = target_dic[key][seg_key].strip()
                    t1=(len(source.split()))
                    src.attrib['words']=str(t1)
                    t2=(len(target.split()))
                    trg.attrib['words']=str(t2)
                    source_word_count+=t1
                    target_word_count+=t2


        else:
            print "Doc not found", key
    root.attrib['sent']=str(par_id)
    root.attrib['source_word']=str(source_word_count)
    root.attrib['target_word']=str(target_word_count)
    tree = ET.ElementTree(root)
    tree.write(output_file, pretty_print=True, encoding='utf-8', xml_declaration=True)

def read_standard(xml_file):
    xml_parser = ET.XMLParser(recover=True,encoding='utf-8',resolve_entities=True )
    xml_tree=ET.parse(xml_file,xml_parser)
    xml_root=xml_tree.getroot()
    par_list=xml_root.findall('p')
    source_list=[[None]]*len(par_list)
    target_list=[[None]]*len(par_list)
    for p in par_list:
        key=int(p.attrib['id'])
        children=p.getchildren()
        source=children[0].text
        target=children[1].text
        source_list[key]=source
        target_list[key]=target
    return (source_list,target_list)

def read_rawtext(source_file,target_file):
    source_file=io.open(source_file,'r',encoding='utf-8')
    target_file=io.open(target_file,'r',encoding='utf-8')
    source_line=source_file.readlines()
    target_line=target_file.readlines()
    source_file.close()
    target_file.close()
    source_line = filter(lambda x: not re.match(r'^\s*$', x), source_line)
    target_line = filter(lambda x: not re.match(r'^\s*$', x), target_line)
    if len(source_line) != len(target_line):
        print  'src,tag',len(source_line) , len(target_line)
        raise TypeError('Incorrect file lines')
    source_dic={}
    source_dic[0]={}
    target_dic={}
    target_dic[0]={}
    for i,line in enumerate(source_line):
        source_dic[0][i]=line
    for i,line in enumerate(target_line):
        target_dic[0][i]=line
    return (source_dic,target_dic)

def read_cdecformat(file):
    file=io.open(file,'r',encoding='utf-8')
    lines=file.readlines()
    file.close()
    lines = filter(lambda x: not re.match(r'^\s*$', x), lines)
    source_dic={}
    source_dic[0]={}
    target_dic={}
    target_dic[0]={}
    for i,line in enumerate(lines):
        toks=line.split('|||')
        target_dic[0][i]=toks[2]
        source_dic[0][i]=toks[1]
    return (source_dic,target_dic)











