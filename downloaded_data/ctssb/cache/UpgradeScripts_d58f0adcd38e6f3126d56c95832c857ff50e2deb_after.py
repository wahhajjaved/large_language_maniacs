#!/usr/bin/python

import sys,copy,os,os.path,traceback,fnmatch
from xml.dom.minidom import *
from generateHelper import *

source_mds_path = ''
dest_mds_path = ''
relative_recur_path = ''
script_gen_path = ''
source_files = []
dest_files = []
debug_flag = 0
curr_source_file = ''
curr_dest_file = ''
warnings = []
id_set = set() #Need to clear after each file script generation

class DebugFlag:
    FINE = 1
    FINER = 2
    FINEST = 3

WARN = '\n##### Warning: NOT GENERATING SCRIPT FOR ABOVE, NOT SUPPORTED  #####\n'

def checkForAttributeChange(manipulate_node,source_node,dest_node):
    global debug_flag,id_set
    if debug_flag >= DebugFlag.FINER: print'\ncheckForAttributeChange():Enter '+printNode(source_node)
    if set(source_node.attributes.items()) == set(dest_node.attributes.items()): #Check if both nodes have same set of key-value pairs then no need to compare or generate scritps
        if debug_flag >= DebugFlag.FINER:
            print printNode(source_node)+' : No Attribute Changed'
            print'checkForAttributeChange():Exit '+printNode(source_node)+'\n'
            return
    if (source_node.hasAttribute('id') and source_node.getAttribute('id') in id_set) or (source_node.parentNode.nodeType == Node.ELEMENT_NODE and source_node.parentNode.hasAttribute('id') and source_node.parentNode.getAttribute('id') in id_set):
        if debug_flag >= DebugFlag.FINE:
            print 'Not required script for Attribute Change in '+printNode(source_node)+' this or parent node is getting inserted'
        return
    attr_set = set(list(source_node.attributes.keys()) + list(dest_node.attributes.keys()))
    if debug_flag >= DebugFlag.FINER : print printNode(source_node)+'  AttributeList: ',attr_set
    while(attr_set):
        attr = attr_set.pop()
        if source_node.hasAttribute(attr) and dest_node.hasAttribute(attr):
            if source_node.getAttribute(attr) == dest_node.getAttribute(attr):
                continue
            else:
                comment = 'Attribute Updated: '+attr+' '+printNode(source_node)+' modified from '+source_node.getAttribute(attr)+' to '+dest_node.getAttribute(attr)
                if debug_flag >= DebugFlag.FINE: print(comment)
                addCommentNode(manipulate_node,comment)
                generateAttributeScript(manipulate_node, 'insert', source_node.nodeName, 'id', source_node.getAttribute('id'),attr, dest_node.getAttribute(attr))
        elif source_node.hasAttribute(attr):
            comment = 'Attribute Removed: '+attr+' '+printNode(source_node)
            if debug_flag >= DebugFlag.FINE : print(comment)
            addCommentNode(manipulate_node,comment)
            generateAttributeScript(manipulate_node, 'remove', source_node.nodeName, 'id', source_node.getAttribute('id'), attr, None)
        else:
            comment =  'Attribute Added: '+attr+' '+printNode(dest_node)
            if debug_flag >= DebugFlag.FINE : print(comment)
            addCommentNode(manipulate_node,comment)
            generateAttributeScript(manipulate_node, 'insert', source_node.nodeName, 'id', source_node.getAttribute('id'),attr, dest_node.getAttribute(attr))
    #Future scope for development
    # What if it reports that all the Attributes of a component has been changed? Don't you think it's just id that got changed? Can you handle this?
    # why so many modify elements in scripts when all the attributes change of a single commponent could be inserted into one modify?
    if debug_flag >= DebugFlag.FINER: print'checkForAttributeChange():Exit '+printNode(source_node)+'\n'
    return


def checkForChildNodeChange(manipulate_node,component_lib_file_root,source_parent_node,dest_parent_node,source_child_node_list,dest_child_node_list):
    global debug_flag,curr_dest_file,warnings,WARN,id_set
    if debug_flag >= DebugFlag.FINER: print '\ncheckForChildNodeChange():Enter '+printNode(source_parent_node)
    if (source_parent_node.hasAttribute('id') and source_parent_node.getAttribute('id') in id_set) or (source_parent_node.parentNode.nodeType == Node.ELEMENT_NODE and source_parent_node.parentNode.hasAttribute('id') and source_parent_node.parentNode.getAttribute('id') in id_set):
        if debug_flag >= DebugFlag.FINE:
            print 'Not required script for Node Change in '+printNode(source_parent_node)+' this or parent node is getting inserted'
        return
    for source_node in source_child_node_list:
        if source_node.hasAttribute('id'):
            comment = 'Component removed: '+printNode(source_node)
            if debug_flag >= DebugFlag.FINE: print comment
            addCommentNode(manipulate_node,comment)
            generaterRemoveNodeScript(manipulate_node,source_node.nodeName,'id',source_node.getAttribute('id'))
        else:
            #to handle the removal of components without id and wihtout any child eg. af:setActionListener
            comment =  '\nComponent Removed: '+printNode(source_node)+'\nElement without id : Experimental Feature. Trying to remove and re-insert Parent'+WARN
            print comment
            warnings.append(comment)
            tryRemoveAndInsertThisNode(manipulate_node,component_lib_file_root,source_node.parentNode)
            break #need to replace it with break.no need to continue in this as the whole parent node is going to get replaced

    for dest_node in dest_child_node_list:
        if (not dest_node.hasAttribute('id') and dest_parent_node.hasAttribute('id')): #and dest_node.hasChildNodes:
            # this will require replacing the whole parent component, no point in continuing, only supporint facet as non-id component.
            comment =  '\nComponent ADDED: '+printNode(dest_node)+'\nComponent without id : Experimental Feature, Trying to remove and re-insert parent node'+'\nWill not check any child node of this parent as whole parent will get re-inserted'+WARN
            print comment
            warnings.append(comment)
            tryRemoveAndInsertThisNode(manipulate_node,component_lib_file_root,dest_node.parentNode)
            return
        elif not dest_node.hasAttribute('id'):#can show an error message and move on instead of exiting
            exitScript(9)

    last_child = None
    for node in dest_parent_node.childNodes:
        if node.hasAttribute('id'):
            last_child = node
    ref_node = None
    for dest_node in dest_child_node_list:
        if not (dest_node.getAttribute('id') in id_set):
            if dest_node.isSameNode(last_child):
                #what if parent node is node without id???
                comment = 'Component ADDED: '+printNode(dest_node)
                if dest_parent_node.hasAttribute('id'):
                    if debug_flag >= DebugFlag.FINE: print comment
                    addCommentNode(manipulate_node,comment)
                    addNodeIdsToSet(id_set,dest_node)
                    generateInsertNodeScript(curr_dest_file,manipulate_node,'child',dest_parent_node.nodeName,'id',dest_parent_node.getAttribute('id'),
                                             component_lib_file_root,dest_node.nodeName,'id',dest_node.getAttribute('id'))
                    new_node = copy.deepcopy(dest_node)
                    component_lib_file_root.appendChild(new_node)
                elif findSameLevelChildWithId(dest_node,ref_node) != None:
                    if debug_flag >= DebugFlag.FINE: print comment
                    addCommentNode(manipulate_node,comment)
                    addNodeIdsToSet(id_set,dest_node)
                    generateInsertNodeScript(curr_dest_file,manipulate_node,'end',ref_node.nodeName,'id',ref_node.getAttribute('id'),component_lib_file_root,dest_node.nodeName,'id',dest_node.getAttribute('id'))
                    new_node = copy.deepcopy(dest_node)
                    component_lib_file_root.appendChild(new_node)
                else:
                    comment = '\n'+comment+'\nCase: Parent doesn\'t have id, parent doesn\'t have any children for END referece node, need to remove and re-insert parentOfParentNode'+WARN
                    print comment +'\nTrying : Experimental Feature'
                    warnings.append(comment)
                    try:
                        tryRemoveAndInsertThisNode(manipulate_node,component_lib_file_root,dest_node.parentNode.parentNode)
                    except Exception:
                        print "Try Failed"
                    # handle case when parent doesn't have id + no child node with id, need to remove and re-insert parent of parent
            else:
                next_sibling = findNextSiblingWithId(dest_node)
                if not next_sibling:
                    comment = 'checkForNodeChange: Should Never Occur Node: '+printNode(dest_node)
                    print comment
                    warnings.append(comment)
                else:
                    comment = 'Component ADDED: '+printNode(dest_node)
                    if debug_flag >= DebugFlag.FINE: print comment
                    addCommentNode(manipulate_node,comment)
                    addNodeIdsToSet(id_set,dest_node)
                    generateInsertNodeScript(curr_dest_file,manipulate_node,'before',next_sibling.nodeName,'id',next_sibling.getAttribute('id'),component_lib_file_root,dest_node.nodeName,'id',dest_node.getAttribute('id'))
                    new_node = copy.deepcopy(dest_node)
                    component_lib_file_root.appendChild(new_node)
    if debug_flag >= DebugFlag.FINER: print 'checkForChildNodeChange():Exit '+printNode(source_parent_node),'\n'


def tryRemoveAndInsertThisNode(manipulate_node,component_lib_file_root,insert_node):#Experimental feature : Should generate warning
    global curr_dest_file,debug_flag,id_set
    if debug_flag >= DebugFlag.FINER: print 'tryRemoveAndInsertThisNode():Enter '+printNode(insert_node)
    if insert_node.getAttribute('id') in id_set:
        print 'Node already inserted as part of another node '+printNode(insert_node)
        return
    if not (insert_node.nodeType == Node.ELEMENT_NODE and insert_node.parentNode.nodeType == Node.ELEMENT_NODE and insert_node.parentNode.hasAttribute('id') ):#c:set child, jsp:root parent both without ids
        print "Experimental : tryRemoveAndInsertThisNode : Failed\t\t"
        warnings.append("Experimental : tryRemoveAndInsertThisNode : Failed\t\t")
        return

    next_sibling = findNextSiblingWithId(insert_node)
    comment = 'tryRemoveAndInsertThisNode : Component ADDED: '+printNode(insert_node)
    if debug_flag >= DebugFlag.FINE: print comment
    addCommentNode(manipulate_node,comment)
    addNodeIdsToSet(id_set,insert_node)
    if not next_sibling:
        generateInsertNodeScript(curr_dest_file,manipulate_node,'child',insert_node.parentNode.nodeName,'id',insert_node.parentNode.getAttribute('id'),component_lib_file_root,insert_node.nodeName,'id',insert_node.getAttribute('id'))
    else:
        generateInsertNodeScript(curr_dest_file,manipulate_node,'before',next_sibling.nodeName,'id',next_sibling.getAttribute('id'),component_lib_file_root,insert_node.nodeName,'id',insert_node.getAttribute('id'))
    new_node = copy.deepcopy(insert_node)
    component_lib_file_root.appendChild(new_node)
    if debug_flag >= DebugFlag.FINER: print 'tryRemoveAndInsertThisNode():Exit '+printNode(insert_node)
    return


def matchAndEliminateNode(to_visit,source_node_list,dest_node_list):
    temp_dest_list = []
    temp_source_list = []
    if debug_flag >= DebugFlag.FINER:
        print '\nmatchAndEliminate():Enter'
        printNodeList('source node list: ',source_node_list)
        printNodeList('destination node list: ',dest_node_list)
    for dest_node in dest_node_list:
        for source_node in source_node_list:
            remove_node_flag = 0
            if (dest_node.nodeName == source_node.nodeName) and ( (source_node.hasAttribute('id') and dest_node.hasAttribute('id') and source_node.getAttribute("id") == dest_node.getAttribute("id")) or set(source_node.attributes.items()) == set(dest_node.attributes.items())):
                if source_node.hasChildNodes() or dest_node.hasChildNodes():
                    visit_node = (source_node,dest_node)
                    to_visit.insert(0,visit_node)
                temp_dest_list.append(dest_node)
                temp_source_list.append(source_node)
        if not (source_node_list and dest_node_list):
            break

    for source_node in temp_source_list: source_node_list.remove(source_node)
    for dest_node in temp_dest_list: dest_node_list.remove(dest_node)
    if debug_flag >= DebugFlag.FINER:
        print 'After Elimination:'
        printNodeList('source node list: ',source_node_list)
        printNodeList('destination node list: ',dest_node_list)
        print 'matchAndEliminate():Exit\n'
    return


def modifiedDFS(to_visit,manipulate_node,component_lib_file_root,meta_registry_node):
    global warnings,curr_dest_file,script_gen_path,id_set
    file_name = os.path.basename(curr_dest_file)
    index = string.find(file_name,'_Layout')
    file_name = file_name[:index]+'.jsff'
    print '\n\n\n************ Modifying : '+file_name+' ********************'
    while(to_visit):
        if debug_flag >= DebugFlag.FINER: print '\nto_visit[]: ',to_visit
        source_parent_node,dest_parent_node = to_visit.pop(0)
        if debug_flag >= DebugFlag.FINER: print 'Now Visiting: '+dest_parent_node.nodeName+' id:'+dest_parent_node.getAttribute('id')
        source_child_node_list = copy.copy(source_parent_node.childNodes)
        dest_child_node_list = copy.copy(dest_parent_node.childNodes)
        source_child_node_list.reverse()
        dest_child_node_list.reverse()
        checkForAttributeChange(manipulate_node,source_parent_node,dest_parent_node)
        matchAndEliminateNode(to_visit,source_child_node_list,dest_child_node_list)
        checkForChildNodeChange(manipulate_node,component_lib_file_root,source_parent_node,dest_parent_node,source_child_node_list,dest_child_node_list)
#    doc = manipulate_node.ownerDocument
#    component_doc = component_lib_file_root.ownerDocument
#    file_name = os.path.basename(curr_dest_file)
#    index = string.find(file_name,'_Layout')
#    file_name = file_name[:index]
#    print ('\n++++++++++++++++++++  WARNINGS : '+file_name+' +++++++++++++++++++++++')
#    for warn in warnings:
#        print warn
#    print("\n\n+++++++++++++++++Upgrade Script++++++++++++++++++++")
#    print(doc.toprettyxml())
#    print("\n+++++++++++++++++ComponentLib File++++++++++++++++++++")
#    print(component_doc.toprettyxml())
    if manipulate_node.hasChildNodes():
        writeScriptsAndModifyRegistry(script_gen_path,curr_dest_file,manipulate_node.ownerDocument,component_lib_file_root.ownerDocument,meta_registry_node)
    id_set.clear()
    return

def initProcess():
    Syntax = 'generateMain.py  old_mds_path  new_mds_path  dir_path_relative_to_mds  script_gen_path  debug_flag(optional)'
    global source_mds_path,dest_mds_path,relative_recur_path,script_gen_path,source_files,dest_files,curr_source_file,curr_dest_file,debug_flag
    to_visit = []

    if not (len(sys.argv) ==5 or len(sys.argv) == 6):
        print("Wrong arguement passed\n"+Syntax)
        exitScript(1)
    source_mds_path = sys.argv[1]
    dest_mds_path = sys.argv[2]
    relative_recur_path = sys.argv[3]
    script_gen_path = sys.argv[4]
    try:
        if(len(sys.argv) == 6):
            debug_flag = int(sys.argv[5])
    except Exception:
        print("Provide integer value for debug flag")
        exitScript(2)

    if not os.access(script_gen_path,os.W_OK):
        print "Script generation path not write accessible : Exiting"
        exitScript(3)

    meta_registry_node = getUpgradeMetaRegistryNode()
    prepareFileList(source_mds_path,dest_mds_path,relative_recur_path,source_files,dest_files,debug_flag)
    for curr_source_file, curr_dest_file in zip(source_files, dest_files):
        if not os.path.basename(curr_source_file) == os.path.basename(curr_dest_file):
            print("mismatch in source and destination files. Make sure both old and new mds contains same files")
            exitScript(4)
        else:
            source_dom = parse(curr_source_file)
            dest_dom = parse(curr_dest_file)
            source_root = source_dom.documentElement
            dest_root = dest_dom.documentElement
            visit_node = (source_root,dest_root)
            to_visit.append(visit_node)
            cleanDOM(source_root)
            cleanDOM(dest_root)
            manipulate_node = getManipulateUpgradeMetaNode(relativePath(curr_dest_file, dest_mds_path))
            component_lib_file_root = getComponentLibFileRoot(dest_dom)
            modifiedDFS(to_visit,manipulate_node,component_lib_file_root,meta_registry_node)
    os.chdir(script_gen_path)
    upgrade_meta_registry_file = open('upgradeMetaRegistry.xml','w+')
    upgrade_meta_registry_file.write(meta_registry_node.ownerDocument.toprettyxml(encoding='UTF-8'))
    upgrade_meta_registry_file.close()
    return




initProcess()

'''to do
If Experimental Feature working fine then need to optimize checkChildNodeChange() Function as there is lot of redundancy
2. push all the warnings into a single file along with those components

5.

debug level
support for only id change
check for possible duplicate id after insert
try to validate xml
not just compared id also the tag

at the moment c:set and jsp:root are the only contnious non-id elements in tree.
'''

'''Done:---
4. creating upgradeMetaRegistry
3. writing the generated scripts in newly created updatemeta and componentLib files
In matchAndEliminateNode() Add support to check if a node without id has similar attributes using sets and subsets, even if I attribute defers we need to generate script for removing and re-inserting parent node
clubbing the all attribute changes in one modify tag
don't just insert, remove and re-insert


'''