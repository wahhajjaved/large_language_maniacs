from protoq.models import *
from xml.etree import ElementTree as ET
from django.conf import settings
logging=settings.LOG
import unittest
from protoq.utilities import atomuri

cimv='http://www.metaforclimate.eu/cim/1.1'
gmd='http://www.isotc211.org/2005/gmd'
gco="http://www.isotc211.org/2005/gco"
typekey='{http://www.w3.org/2001/XMLSchema-instance}type'

def getText(elem,path):
    ''' Return text from an element ... if it exists '''
    e=elem.find('{%s}%s'%(cimv,path))
    if e is None: 
        return ''
    else:
        return e.text or ''
    
def getText2(elem,path):
    e=elem.find(path)
    if e is None: 
        return '' 
    else: return e.text or ''
    
def getTextN(elem,path):
    r=getText(elem,path)
    if r=='':
        return None
    else: return r
    
def metaAuthor(elem):
    ''' Oh what a nasty piece of code this is, but I don't have time to do it properly '''
    #FIXME do this properly with lxml and xpath with namespaces
    s=ET.tostring(elem)
    if s.find('Charlotte')>-1: 
        n='Charlotte Pascoe'
        c=ResponsibleParty.objects.filter(name=n)
        if len(c)==0:
            p=ResponsibleParty(name=n,abbrev=n,uri=atomuri(),
                               email='Charlotte.Pascoe@stfc.ac.uk')
            p.save()
        else: p=c[0]
    elif s.find('Gerard')>1:
        n='Gerard Devine'
        c=ResponsibleParty.objects.filter(name=n)
        if len(c)==0:
            p=ResponsibleParty(name=n,abbrev=n,uri=atomuri(),
                            email='g.m.devine@reading.ac.uk')
            p.save()
        else: p=c[0]
    else: p=None
    logging.debug('Metadata maintainer: %s'%p)
    return p


def numericalRequirement (elem):
    
    args={'docid':getText(elem,'id')}
    for a in ['description','name']:args[a]=getTextN(elem,a)
    
    if typekey in elem.attrib.keys():
        ctype=elem.attrib[typekey]
    else: ctype='NumericalRequirement'
    v=Vocab.objects.get(name='NumReqTypes')
    ctypeVals=Term.objects.filter(vocab=v)
    try:
        ctype=ctypeVals.get(name=ctype)
    except:
        logging.info('Invalid numerical requirement type [%s] - from %s'%(ctype,args))
        return None
    args['ctype']=ctype
    
    if str(ctype)=='SpatioTemporalConstraint':
        # anyone else think these frequency units should be periods?
        myvocab={'frequencyUnits':'FreqUnits',
                 'averagingUnits':'FreqUnits',
                 'spatialResolutionUnits':'SpatialResolutionTypes'}
        op=elem.find('{%s}outputPeriod'%cimv)
        args['outputPeriod']=outputPeriod(op)
            
        for a in ['temporalAveraging','outputFrequency']:
            args[a]=getTextN(elem,a)
        for a in ['frequencyUnits','averagingUnits','spatialResolution']:
            vv=getTextN(elem,a)
            if vv:
                v=Vocab.objects.get(name=myvocab[a])
                try:
                    val=Term.objects.filter(vocab=v).get(name=vv)
                    args[a]=val
                except:
                    logging.info('Invalid unit %s not found in vocab %s'%(vv,v))
        n=SpatioTemporalConstraint(**args)
        logging.debug('spatio temporal constraint has args %s'%args)
    else:
        n=NumericalRequirement(**args)
    n.save()
    
    for r in elem.findall('{%s}numericalRequirement'%cimv):
        nn=numericalRequirement(r)
        if nn: n.consistsOf.add(nn)

    # Now make sure we return the numerical requirement not any subclasses
    # Not sure I need to do this, but just in case ...
    try:
        sc=n.__getattribute__('numericalrequirement_ptr')
        return sc  # return the parent class
    except AttributeError:
        return n
        
def outputPeriod(elem):
    ''' Handle the output period of a spatio temporal constraint '''
    o=duration(elem,None)
    if elem.text: o.description=elem.text
    return o

def duration(elem,calendar):
    if elem is None:
        return None
    try:
        etxt=getText(elem,'lengthYears')
        length=float(etxt)
    except:
        logging.info('Unable to read length from %s'%etxt)
        length=None
    d=ClosedDateRange(startDate=getTextN(elem,'startDate'),
                            endDate=getTextN(elem,'endDate'),
                            length=length,
                            calendar=calendar)
    d.save()
    logging.debug('Experiment duration %s'%d)
    return d
        
def calendar(elem):
    cvalues=Term.objects.filter(vocab=Vocab.objects.get(name='CalendarTypes'))
    cnames=[str(i) for i in cvalues]
    if elem:
        cc=elem[0].tag.split('}')[1]
        if cc in cnames:
            return cvalues.get(name=cc)
        else:
            logging.info('Did not find calendar type '+cc) 
    else:
        logging.debug('Could not find calendar')
    return None

class NumericalExperiment(object):
    ''' Handles the reading of a numerical experiment, and the insertion into the django db '''
    
    def __init__(self,filename):
        ''' Reads CIM format numerical experiments, create an experiment, and then link
        the numerical requirements in as well'''
        
        etree=ET.parse(filename)
        txt=open(filename,'r').read()
        logging.debug('Parsing experiment filename %s'%filename)
	
        root=etree.getroot()
        
        #basic document stuff, note q'naire doc not identical to experiment bits ...
        doc={'description':'description','shortName':'abbrev','longName':'title'}
        for key in doc:
            self.__setattr__(doc[key],getText(root,key))
        
        self.rationale=getText(root,key)
        #calendar before date
        self.calendar=calendar(root.find('{%s}calendar'%cimv))
        self.requiredDuration=duration(root.find('{%s}requiredDuration'%cimv),self.calendar)
        
        # going to ignore the ids in the file, and be consistent with the rest of the q'naire
        # documents
      
        # bypass reading all that nasty gmd party stuff ...
        author=metaAuthor(root.find('{%s}author'%cimv))
        
        # do some quick length checking
        if len(self.abbrev)>25:
            old=self.abbrev
            self.abbrev=old[0:24]
            logging.info('TOOLONG: Truncating abbreviation %s to %s'%(old,self.abbrev))

        E=Experiment(rationale=self.rationale,
                     description=self.description,
                     uri=atomuri(),
                     abbrev=self.abbrev,
                     title=self.title,
                     requiredDuration=self.requiredDuration,
                     requiredCalendar=self.calendar,
                     metadataMaintainer=author)
        E.save()
        
        for r in root.findall('{%s}numericalRequirement'%cimv):
            n=numericalRequirement(r)
            E.requirements.add(n)
            
        # we can save this most expeditiously, directly, here.
        keys=['uri','metadataVersion','documentVersion','created','updated','author','description']
        attrs={}
        for key in keys: attrs[key]=E.__getattribute__(key)
        
        cfile=CIMObject(**attrs)
        cfile.cimtype=E._meta.module_name
        cfile.xmlfile.save('%s_%s_v%s.xml'%(cfile.cimtype,E.uri,E.documentVersion),
                               ContentFile(txt),save=False)
        cfile.title='%s (%s)'%(E.abbrev,E.title)
        cfile.save()   
        
class TestFunctions(unittest.TestCase): 
    def testExperiment(self):
        import os
        d='data/experiments/'
        for f in os.listdir(d):
            if f.endswith('.xml'):
                x=NumericalExperiment(os.path.join(d, f)) 
               

        
        
            
        