from copy import copy
import logging

from BeautifulSoup import BeautifulSoup

from zope import component
from zope.annotation.interfaces import IAnnotations

from plone.contentrules.engine.assignments import RuleAssignment
from plone.contentrules.engine.interfaces import IRuleAssignmentManager
from plone.contentrules.engine.interfaces import IRuleStorage

from plone.app.contentrules.rule import get_assignments

from Products.AdvancedQuery import Or, Eq, And, In, Not
from Products.PloneHelpCenter.content.FAQFolder import HelpCenterFAQFolder
from Products.CMFCore.WorkflowCore import WorkflowException

from p4a.subtyper.interfaces import ISubtyper

log = logging.getLogger('faq_centralisation_helper')

QUESTION_TAGS = ["strong", "h3", "h2", "b"]

def run(self):
    import pdb; pdb.set_trace()
    faqs = create_faqs_folder(self)
    faq_docs = get_possible_faqs(self)
    parents = get_faq_containers(faq_docs)
    parse_and_create_faqs(self, faqs, faq_docs)
    add_content_rule_to_containers(parents)
    subtype_containers(parents)
    raise 'hello'
    return 'done'


def create_faqs_folder(self):
    log.info('create_faqs_folder')
    # XXX:
    # langfolder = self.portal_url.getPortalObject()['en']
    langfolder = self.portal_url.getPortalObject()
    langfolder.manage_renameObjects(['faq'], ['faq-old'])
    langfolder._setObject('faq', HelpCenterFAQFolder('faq'))
    faq = langfolder._getOb('faq')
    for lang in self.portal_languages.getSupportedLanguages():
        if lang == 'en':
            continue

        trans_faq = faq.getTranslation(lang)
        if trans_faq is not None:
            trans_faq.aq_parent.manage_renameObjects(['faq'], ['faq-old'])

        faq.addTranslation(lang)
    return faq
    

def get_possible_faqs(self):
    log.info('get_possible_faqs')
    queries = []
    title = In('Title', ["*frequently*", "*faq*", "FAQ*", "Frequently*"])
    portal_type = In("portal_type",  ["Document", "RichDocument", "Folder"])
    ids = ["faq", "faq.php", "faq.stm", "faqs"]
    for i in range(0, 10):
        ids.append('faq%d.stm' % i)
        ids.append('faq0%d.php' % i)

    id = In('getId', ids)
    body = Eq('SearchableText', "FAQ")
    fop = Eq('path', '/osha/portal/fop')
    advanced_query = And(Or(id, title, body), portal_type, Not(fop))
    ls =  self.portal_catalog.evalAdvancedQuery(advanced_query, (('Date', 'desc'),) )

    # ls = self.portal_catalog(
    #             getId='faq2.stm',
    #             path='/osha/portal/en/good_practice/topics/')

    log.info("Processing FAQs: %s" % "\n".join([i.getURL() for i in ls]))

    odict = {}
    for l in ls:
        o = l.getObject()
        odict[o.absolute_url()] = o
        ts = o.getTranslations().values()
        for t in ts:
            odict[t[0].absolute_url()] = t[0]

    objects = odict.values()
    return objects

    k = ['/'.join(o.getPhysicalPath()) for o in objects]
    k.sort()
    display_str = '\n'.join(k) or 'none'
    return display_str


def get_faq_containers(ls):
    log.info('get_faq_containers')
    parents = {}
    for l in ls:
        if l.portal_type == 'Folder':
            p = l
        else:
            p = l.aq_parent

        parents['/'.join(p.getPhysicalPath())] = p

    return parents

    display_str = '\n'.join([p.absolute_url() for p in parents.values()]) or 'none'
    return display_str


def create_faq(self, question_text, answer_text, state, faq_folder, obj, path=None):
    log.info('create_faq')
    wf = self.portal_workflow
    faq_id = faq_folder.generateUniqueId()
    faqid = faq_folder.invokeFactory('HelpCenterFAQ', faq_id)
    faq = faq_folder.get(faqid)
    faq.setTitle(question_text)
    faq.setDescription(unicode(question_text))
    faq.setAnswer(unicode(answer_text))
    faq.setLanguage(obj.getLanguage())
    faq._renameAfterCreation(check_auto_id=True)
    faq.reindexObject()
    # # Set aliases
    # if path:
    #    rtool = self.portal_redirection
    #    rtool.addRedirect(path, '/'.join(faq.getPhysicalPath()))
    if state == 'published':
        try:
            wf.doActionFor(faq, "submit")
        except WorkflowException:
            pass

    set_keywords(faq, obj.aq_parent)
            

def parse_and_create_faqs(self, faq_folder, faq_docs):
    log.info('parse_and_create_faqs')
    wf = self.portal_workflow
    for obj in faq_docs:
        chain = wf.getChainFor(obj)
        status = self.portal_workflow.getStatusOf(obj, chain[0])
        state = status["review_state"]

        if obj.portal_type == 'Folder':
            QA_dict = parse_folder_faq(obj)
            for path, question_text, answer_text in QA_dict.items():
                create_faq(question_text, answer_text, state, faq_folder, obj)

        else:
            QA_dict = parse_document_faq(obj)
            for question_text, answer_text in QA_dict.items():
                create_faq(question_text, answer_text, state, faq_folder, obj)


def parse_folder_faq(folder):
    log.info('parse_folder_faq')
    QA_dict = {}
    faq_docs = folder.objectValues()
    for faq in faq_docs:
        if not faq.Title():
            continue # Ignore turds

        QA_dict['/'.join(faq.getPhysicalPath())] =  (faq.Title(), faq.getText())
    return QA_dict


def parse_document_faq(doc):
    log.info('parse_document_faq')
    QA_dict = {}
    body = doc.CookedBody()
    soup = BeautifulSoup(body)
    # Remove breadcrumb links
    for crumb in soup.findAll("p", {"class" : "crumb"}):
        if not crumb.contents:
            crumb.extract()
    for link in soup.findAll("a"):
        if link.has_key("href"):
            if link["href"] == "#top":
                # Remove links to the top of the page
                link.extract()
            elif link.has_key("name")\
                     and not link.has_key("href"):
                # Remove anchors
                # todo: remove but keep contents
                cnts = copy(link.contents)
                cnts.remove(" ")
                if len(cnts) == 0:
                    link.extract()
                elif len(cnts) == 1:
                    link.replaceWith(cnts)
                else:
                    log.info(
                        "The anchor:%s contains more than one element"\
                        %unicode(link)
                        )

    possible_questions = []
    for tag in QUESTION_TAGS:
        possible_questions += soup.findAll(tag)

    probable_questions = []
    for question in possible_questions:
        if is_probable_question(question.parent):
            if " " in question.parent.contents:
                question.parent.contents.remove(" ")
            probable_questions += question.parent
        elif is_probable_question(question):
            probable_questions += question

    log.info("Probable Questions in this Document: %s"\
             %"\n".join([unicode(i) for i in probable_questions]))
    question_text = ''
    answer_text = ''
    for question in probable_questions:
        answer_text = ""
        question_text = unicode(question.string)

        for answer in question.parent.nextSiblingGenerator():
            if is_probable_question(answer):
                break
            elif hasattr(answer , "name") and answer.name in ["h1", "h2", "h3"]:
                break
            else:
                answer_text += unicode(answer)

        while QA_dict.get(question_text):
            log.info('Duplicate question in QA_dict found')
            question_text += ' '

        # If there is no answer then it wasn't a question
        if answer_text and answer_text not in ["\n", " "]:
            # log.info("\nQ:%s\nA:%s" %(question_text, answer_text))
            QA_dict[question_text] = answer_text

    return QA_dict


def is_probable_question(suspect):
    # <h2>Q...
    # <h3>Q...
    # <p><strong>Q..
    # <p><b>Q..
    # endswith("?")

    if hasattr(suspect, "name"):
        if suspect.name in ["h2", "h3"]:
            if suspect.string\
                   and suspect.string.strip().endswith("?"):
                return True

        elif suspect.name in ["a", "p"]:
            if hasattr(suspect, "contents"):
                # .contents returns a list of the subelements
                cnts = copy(suspect.contents)
                if " " in cnts:
                    cnts.remove(" ")
                if cnts:
                    first_item = cnts[0]
                    if hasattr(first_item, "name"):
                        if first_item.name in QUESTION_TAGS:
                            if first_item.string\
                                   and first_item.string.strip().endswith("?"):
                                return True
                                

def set_keywords(faq, old_parent):
    log.info("set_keywords")
    for fid, kw  in [
            ('disability', 'disability'),
            ('young_people', 'young_people'),
            ('agriculture', 'agriculture'),
            ('construction', 'construction'),
            ('education', 'education'),
            ('fisheries', 'fisheries'),
            ('healthcare', 'healthcare'),
            ('accident_prevention', 'accident_prevention'),
            ('dangerous_substances', 'dangerous_substances'),
            ('msds', 'msd'),
            ('msd', 'msd'),
            ]:
        if fid in old_parent.getPhysicalPath():
            try:
                subject = old_parent.getSubject()
            except:
                subject = old_parent.Schema().getField('subject').get(old_parent)

            if kw not in subject:
                subject = list(subject) + [kw]
                old_parent.setSubject(subject)
                log.info("Add keyword '%s' to %s: %s \n" \
                        % (kw, old_parent.portal_type, old_parent.getPhysicalPath()))
            else:
                log.info("Keyword '%s' already in %s: %s \n" \
                        % (kw, old_parent.portal_type, old_parent.getPhysicalPath()))
                        
            log.info('Added keyword to FAQ %s, %s' % ('/'.join(faq.getPhysicalPath(), kw)))


def subtype_containers(parents):
    subtyper = component.getUtility(ISubtyper)
    for parent in parents:
        if subtyper.existing_type(parent) is None:
            subtyper.change_type(parent, 'slc.aggregation.aggregator')
            if not parent.isCanonical():
                canonical = parent.getCanonical()
            else:
                canonical = parent

            subtyper.change_type(canonical, 'slc.aggregation.aggregator')
            annotations = IAnnotations(canonical)
            annotations['content_types'] =  ['HelpCenterFAQ']
            annotations['review_state'] = 'published'
            annotations['aggregation_sources'] = ['/en/faqs']
            keywords = []
            for fid, kw  in [
                    ('disability', 'disability'),
                    ('young_people', 'young_people'),
                    ('agriculture', 'agriculture'),
                    ('construction', 'construction'),
                    ('education', 'education'),
                    ('fisheries', 'fisheries'),
                    ('healthcare', 'healthcare'),
                    ('accident_prevention', 'accident_prevention'),
                    ('dangerous_substances', 'dangerous_substances'),
                    ('msds', 'msd'),
                    ('msd', 'msd'),
                    ]:

                if fid in parent.getPhysicalPath():
                    keywords.append(kw)

            annotations['keyword_list'] = keywords
            annotations['restrict_language'] = False
            log.info('%s subtyped as aggregator with keywords %s' % ('/'.join(parent.getPhysicalPath(), str(keywords))))


def add_content_rule_to_containers(parents):
    log.info('add_content_rule_to_containers')
    rule_id = 'rule-7'
    storage = component.queryUtility(IRuleStorage)
    rule = storage.get(rule_id)

    for parent in parents:
        assignments = IRuleAssignmentManager(parent, None)
        get_assignments(storage[rule_id]).insert('/'.join(parent.getPhysicalPath()))
        rule_ass = RuleAssignment(ruleid=rule_id, enabled=True, bubbles=True)

        assignments[rule_id] = rule_ass
        log.info("Content Rule '%s' assigned to %s \n" % (rule_id, parent.absolute_url()))

