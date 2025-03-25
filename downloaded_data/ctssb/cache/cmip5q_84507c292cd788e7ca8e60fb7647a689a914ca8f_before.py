# -*- coding: utf-8 -*-
from datetime import datetime
from django.db import models
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes import generic
from django import forms
from django.forms.util import ErrorList
from django.core.urlresolvers import reverse
from django.db.models.query import CollectedObjects, delete_objects
from django.db.models.fields.related import ForeignKey
from django.contrib.sites.models import Site, RequestSite

from lxml import etree as ET

from django.core import exceptions
from django.utils.translation import ugettext_lazy, ugettext as _

from django.db.models import permalink
from django.core.files import File

from atom import Feed
from cmip5q.protoq.cimHandling import *
from cmip5q.protoq.utilities import atomuri,HTMLdate
from cmip5q.XMLutilities import *
from cmip5q.protoq.fields import *
from cmip5q.protoq.dropdown import TimeLengthWidget

from django.conf import settings
logging=settings.LOG
from django.core.files.base import ContentFile
from django.db.models.query import QuerySet
import types

cimv='http://www.metaforclimate.eu/cim/1.4'
gmd='http://www.isotc211.org/2005/gmd'
gco="http://www.isotc211.org/2005/gco"


def soft_delete(obj,simulate=False):
    ''' This method provided to use to override native model deletes to avoid
    cascade on delete ... the first requirement is only in responsible parties,
    but it may exist elsewhere, so we put it up here as a standalone method.
    If simulate is passed as true, we don't actually do the delete ... but
    see if we could have done it.
          The method returns a tuple boolean and dict. The boolean will be true if 
    it is possible to delete the object (nothing links to it). If the booleaan
    is false, then the dict is a dictionary keyed by models into instances which link 
    to it, and which need to be unlinked before a delete can occur.'''
    # with help from stack overflow
    
    assert obj._get_pk_val() is not None, "%s object can't be deleted because its %s attribute is set to None." % (
                      obj._meta.object_name, obj._meta.pk.attname)

    # My first attempt to do this was simply to override the django delete 
    # method and only delete the actual instance, but this can leave the
    # related objects with hanging links to nothing ... which can then
    # be replaced with the *wrong* objects ... so we either have an error
    # or wrong data ... no, no, no ...
    # seen_objs = CollectedObjects()
    # seen_objs.add(model=obj.__class__, pk=obj.pk, obj=obj, parent_model=None)
    # delete_objects(seen_objs)

    on_death_row = CollectedObjects()
    obj._collect_sub_objects(on_death_row)
    # and ideally clear them all ... but that's hard, and impossible if
    # they don't have null=True ... wait til this gets fixed in django.
    # Meanwhile just return the list of direct linkers 
    # NB: odr={klass1:{id1:instance, id2:instance ...},klass2:{...}}
    klass=obj.__class__
    n=0  # number of objects to be deleted
    for k in on_death_row.unordered_keys():
        n+=len(on_death_row[k]) 
    # before we go following the foreign keys, let's just make sure some of these
    # objects are not simply parent objects in a non abstract class heirarchy.
    # we should allow those to be deleted happily.
    if hasattr(obj,'get_parent_model'):
        # then we know we have at least one parent object to get rid of, and if it's the only one,
        # delete with impunity.
        parent=obj.get_parent_model()
        if len(on_death_row[parent])==1: 
            n=1
        else:
            logging.info('This case not coded for ... sorry ')
            raise NotImplementedError
        
    if n<>1:
        #delve into the metadata to find out what managers point at this model,
        #then use all those to filter out direct relationships to this one.
        related_models=on_death_row.keys()
        # now find all the foreign keys
        directly_linked_models=[]
        fkeys={}
        linkdict={}
        for model in related_models:
            for f in model._meta.fields:
                if isinstance(f, ForeignKey) and f.rel.to == klass: 
                    if model not in directly_linked_models:directly_linked_models.append(model)
                    # get the foreign keys for later use 
                    if model in fkeys:
                        if f not in fkeys[model]: 
                            fkeys[model].append(f)
                    else:
                        fkeys[model]=[f]
        # parse the instances to check they link to this one
        # start by rejecting models which don't actually have a foreign key into this objects class
        for model in related_models:
            if model not in directly_linked_models: del(on_death_row.data[model])
        # now parse the instances and see if they have any direct link to this one (they might
        # be in the list because they link to objects that link to this one, even though they have fks
        # that would allow direct links).
        # it's probably be cleaner to go backwards ... now we know the foreign keys, we should
        # be able to get querysets and see if the object is in the queryset ... but this works too.
        for model in on_death_row.unordered_keys():
            # find all the foreign keys to the object.
            for id in on_death_row.data[model]:
                referer=on_death_row.data[model][id]
                for fk in fkeys[model]:
                    fk_value = getattr(referer, "%s_id" % fk.name)
                    if fk_value is not None:
                        mname=model._meta.module_name
                        if mname not in linkdict: linkdict[mname]=[] 
                        linkdict[mname].append(referer)
        return False,linkdict
    
    if not simulate: delete_objects(on_death_row)
    return True,{}

class ChildQuerySet(QuerySet):
    ''' Used to support the queryset options on ParentModel'''
    def iterator(self):
        for obj in super(ChildQuerySet, self).iterator():
            yield obj.get_child_object()

class ChildManager(models.Manager):
    ''' Used to provide a manager for children of a ParentModel '''
    def get_query_set(self):
        return ChildQuerySet(self.model)

class ParentModel(models.Model):
    
    ''' This abstract class is used to subclasses base classes that we want
    themselves to work with further subclasses, in such a way that we can
    get down from a parent instance to a child instance, and have sensible
    query sets. See http://www.djangosnippets.org/snippets/1037/'''
    
    _child_name = models.CharField(max_length=100, editable=False)
    objects = models.Manager()
    children = ChildManager()
    form=None   # we replace this when we instantiate ...

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        self._child_name = self.get_child_name()
        super(ParentModel, self).save(*args, **kwargs)

    def get_child_name(self):
        if type(self) is self.get_parent_model():
            return self._child_name
        return self.get_parent_link().related_query_name()

    def get_child_object(self):
        return getattr(self, self.get_child_name())

    def get_parent_link(self):
        return self._meta.parents[self.get_parent_model()]

    def get_parent_model(self):
        raise NotImplementedError


class EditHistoryEvent(models.Model):
    ''' Used for edit history event logging '''
    eventDate=models.DateField(auto_now_add=True,editable=False)
    eventParty=models.ForeignKey('ResponsibleParty')
    eventAction=models.TextField(blank=True)
    # following will only means something to whatever creates the event.
    eventIdentifier=models.CharField(max_length=128)

class Fundamentals(models.Model):
    ''' These is an abstract class carrying fundamentals in common between CIM documents
    as currently described in the questionnaire, and CIM documents as exported from the
    questionnaire. It's a convenience class for the questionnaire alone '''
    # The URI should only change if the thing described by the document changes.
    # That is, once assigned, the URI never changes, and once exported, the document should persist.
    # If the thing itself changes, we should copy the document, give it a new URI, and update it ...
    # The uri appears in subclasses, because it needs to be unique in the Doc children, but is
    # allowed to be duplicated in the CIMObjects (albeit not with the same metadataversion and 
    # document version.
    #
    # However, we can have descriptions which differ because the way we describe it has changed,
    # if that happens, we should modify the version identifier which follows AND the documentVersion.
    metadataVersion=models.CharField(max_length=128,editable=False)
    # The following should only be updated when the document is valid, and the document has
    # been exported as a new version. However, note that while it is possible in principle for
    # this to change with subcomponents, it's not likely as currently implemented.
    documentVersion=models.IntegerField(default=1,editable=False)
    
    class Meta:
        abstract=True
 
class CIMObject (Fundamentals):
    ''' This is an exported CIM object. Once exported, the questionnaire can't molest it,
    but it's included here, because the questionnaire can return it '''
    uri=models.CharField(max_length=64,editable=False)    
    cimtype=models.CharField(max_length=64,editable=False)
    xmlfile=models.FileField(upload_to='PersistedXML')
    # These are update by the parent doc, which is why they're not "fundamentals"
    created=models.DateField(editable=False)
    updated=models.DateField(editable=False)
    # The following attributes are needed to provide "discovery" via atom entries:
    author=models.ForeignKey('ResponsibleParty',blank=True,null=True,related_name='%(class)s_author')
    title=models.CharField(max_length=128,blank=True,null=True)
    description=models.TextField(blank=True)
    @models.permalink
    def get_absolute_url(self):
        return ('cmip5q.protoq.views.persistedDoc',(self.cimtype,self.uri,self.documentVersion))
    def save(self,*args,**kwargs):
        ''' We should have a local save method to ensure the version policy is not broken '''
        # FIXME
        return Fundamentals.save(self,*args,**kwargs)
    
    
class Doc(Fundamentals):
    ''' Abstract class for general properties of the CIM documents handled in the questionnaire '''
    
    # Parties (all documents are associated with a centre)
    centre=models.ForeignKey('Centre',blank=True,null=True)
    author=models.ForeignKey('ResponsibleParty',blank=True,null=True,related_name='%(class)s_author')
    funder=models.ForeignKey('ResponsibleParty',blank=True,null=True,related_name='%(class)s_funder')
    contact=models.ForeignKey('ResponsibleParty',blank=True,null=True,related_name='%(class)s_contact')
    metadataMaintainer=models.ForeignKey('ResponsibleParty',blank=True,null=True,
                       related_name='%(class)s_metadataMaintainer')
    
    uri=models.CharField(max_length=64,unique=True,editable=False)
    title=models.CharField(max_length=128,blank=True,null=True)
    abbrev=models.CharField(max_length=40)
    description=models.TextField(blank=True)
   
    # next two are used to calculate the status bar, and are filled in by the validation software
    validErrors=models.IntegerField(default=-1,editable=False)
    numberOfValidationChecks=models.IntegerField(default=0,editable=False)
    # following is used by the user to declare the document is "ready"
    isComplete=models.BooleanField(default=False)
    # to be used for event histories:
    editHistory=models.ManyToManyField(EditHistoryEvent,blank=True,null=True)
    # next two are automagically populated
    created=models.DateField(auto_now_add=True,editable=False)
    updated=models.DateField(auto_now=True,editable=False)
    class Meta:
        abstract=True
        ordering=['abbrev','title']
        
    def status(self):
        ''' Return a percentage completion in terms of validation '''
        if self.validErrors<>-1 and self.numberOfValidationChecks<>0:
            return int(100.0*(1.0-float(self.validErrors)/self.numberOfValidationChecks))
        else: return 0.0
        # FIXME: and eventually see if we have a children attribute and sum them up ...
    
    def qstatus(self):
        ''' This is a convenience method which returns an overarching status from:
          '[invalid; valid, but not submitted; and submitted] '''
        if self.isComplete:
            return 'done'
        elif self.status<>100.0:
            return 'undone'
        else: return 'ready'
    
    def xmlobject(self):
        ''' Return an lxml object view of me '''
        from cmip5q.protoq.Translator import Translator  # needs to be deferred down here to avoid circularity
        translator=Translator()
        if self._meta.module_name=='simulation' :
            # composition defaults to false
            translator.setComponentOptions(recurse=True,composition=True)
        return translator.q2cim(self,docType=self._meta.module_name)
    
    def xml(self):
        ''' Return an xml string version of me '''
        if len(self.XMLO): self.XMLO=self.xmlobject()
        return ET.tostring(self.XMLO,pretty_print=True)
    
    def validate(self):
        ''' All documents should be validatable '''
        v=Validator()
        self.XMLO=self.xmlobject()
        v.validateDoc(self.XMLO,cimtype=self._meta.module_name)
        self.validErrors=v.nInvalid
        self.numberOfValidationChecks=v.nChecks
        logging.debug("%s validate checks=%s"%(self._meta.module_name,self.numberOfValidationChecks))
        logging.debug("%s validate errors=%s"%(self._meta.module_name,self.validErrors))
        self.save()
        return v.valid,v.errorsAsHtml()
# FIXME: This moved from component to here ... needs something done eventually ...
#    def validate(self):
#        # I don't work yet as I need my local component_id
#       ''' Check to see if component is valid. Returns True/False '''
#        nm=NumericalModel(Centre.objects.get(id=self.centre_id),component_id)
#        CIMDoc=nm.export(recurse=False)
#       sct_doc = ET.parse("xsl/BasicChecks.sch")
#        schematron = ET.Schematron(sct_doc)
#        return schematron.validate(CIMFragment)
    
        
    def export(self):
        ''' Make available for export in the atom feed '''
        # first redo validation to make sure this really is ok
        if self.isComplete:
            return False,'This document has already been exported',None
        valid,html=self.validate()
        #logging.info('WARNING Exporting document for ESG regardless of validation state')
        #valid=True # FIXME
        self.isComplete=valid
        self.save(complete=self.isComplete) # make that completeness status last.
        if self.isComplete: 
            # now store the document ... 
            keys=['uri','metadataVersion','documentVersion','created','updated','author','description']
            attrs={}
            for key in keys: attrs[key]=self.__getattribute__(key)
            cfile=CIMObject(**attrs)
            cfile.cimtype=self._meta.module_name
            cfile.xmlfile.save('%s_%s_v%s.xml'%(cfile.cimtype,self.uri,self.documentVersion),
                               ContentFile(self.xml()),save=False)
            cfile.title='%s (%s)'%(self.abbrev,self.title)
            cfile.save()
            return True,'Version %s of %s document %s has been permanently stored'%(self.documentVersion,cfile.cimtype,self.uri),cfile.get_absolute_url()
        else:
            return False,'Unable to export invalid document',None
            
    
    def __unicode__(self):
        return self.abbrev
   
    def save(self,*args,**kwargs):
        ''' Used to decide what to do about versions. We only increment the document version
        number with changes once the document is considered to be complete and valid '''
        if 'complete' in kwargs:
            self.isComplete=kwargs['complete']
            del kwargs['complete']
        elif self.isComplete:
            # this is a save AFTER we've marked it complete, so it must be a change.  
            self.isComplete=False
            self.documentVersion+=1
            self.validErrors=-1   # now force a revalidation before any future document incrementing.
        if 'eventParty' in kwargs:
            self.editHistory.add(EditHistoryEvent(eventParty=kwargs['eventParty'],eventIdentifier=self.documentVersion))
        if not self.uri:
            uri=atomuri()
            logging.debug('Missing uri %s assigned for document type %s'%(uri,self._meta.module_name))
            self.uri=uri
        return Fundamentals.save(self,*args,**kwargs)
    
    def delete(self,*args,**kwargs):
        ''' Avoid deleting documents which have foreign keys to this instance'''
        return soft_delete(self,*args,**kwargs)
        
    def delete4real(self):
        ''' Don't bugger round, just blow me away ... and accept that if anything points to me,
        they're history too'''
        return Fundamentals.delete(self)
        
    @models.permalink
    def edit_url(self):
        ''' How can we edit me? '''
        return ('cmip5q.protoq.views.%sEdit'%self._meta.module_name,(self.centre_id,self.id,))
  
class Relationship(models.Model):
    ''' Used to describe relationships between entities '''
    # if we have a controlled vocab for the relationships, it's this one.
    vocab=models.ForeignKey('Vocab',blank=True,null=True)
    # and it's this member of that vocabulary
    value=models.ForeignKey('Term',blank=True,null=True)
    # but sometimes we can't do it with just a term, so let's have some text too.
    description=models.TextField(blank=True,null=True)
    def __unicode__(self):
        if self.value:
            if self.description:
                return '%s %s (%s)'%(self.value,self.sto,self.description)
            else: return '%s %s'%(self.sto,self.value)
        else: return '%s %s'%(self.sto,self.description)
    class Meta:
        abstract=True

class SimRelationship(Relationship):
    sfrom=models.ForeignKey('Simulation',related_name='related_from')
    sto=models.ForeignKey('Simulation',related_name='related_to',blank=True,null=True)

class ResponsibleParty(models.Model):
    ''' So we have the flexibility to use this in future versions '''
    isOrganisation=models.BooleanField(default=False)
    name=models.CharField(max_length=256,blank=True)
    webpage=models.CharField(max_length=128,blank=True)
    abbrev=models.CharField(max_length=25)
    email=models.EmailField(blank=True)
    address=models.TextField(blank=True)
    uri=models.CharField(max_length=64,unique=True)
    centre=models.ForeignKey('Centre',blank=True,null=True) # for access control
    def __unicode__(self):
        return self.abbrev
    def delete(self,*args,**kwargs):
        return soft_delete(self,*args,**kwargs)
    class Meta:
        ordering=['abbrev','name','email']
    @staticmethod
    def fromXML(elem):
        ''' This is an interface class to return either an existing resonsible party instance
        or create a new one from XML '''
        # FIXME
        s=ET.tostring(elem)
        if s.find('Charlotte')>-1: 
            n='Charlotte Pascoe'
            c=ResponsibleParty.objects.filter(name=n).order_by('id')
            if len(c)==0:
                p=ResponsibleParty(name=n,abbrev=n,uri=atomuri(),
                                email='Charlotte.Pascoe@stfc.ac.uk')
                p.save()
            else: p=c[0]
        elif s.find('Gerard')>1:
            n='Gerard Devine'
            c=ResponsibleParty.objects.filter(name=n).order_by('id')
            if len(c)==0:
                p=ResponsibleParty(name=n,abbrev=n,uri=atomuri(),
                                email='g.m.devine@reading.ac.uk')
                p.save()
            else: p=c[0]
        else: p=None
        logging.debug('Metadata maintainer: %s'%p)
        return p

class Centre(ResponsibleParty):
    ''' A CMIP5 modelling centre '''
    # It's such an important entity it gets it's own sub class ...
    # I wanted to preserve the API, but title will need to change to name
    party=models.OneToOneField(ResponsibleParty,parent_link=True,related_name='party')
    def __init__(self,*args,**kwargs):
        ResponsibleParty.__init__(self,*args,**kwargs)
        
class BaseTerm(models.Model):
    name=models.CharField(max_length=256)
    note=models.CharField(max_length=256,blank=True)
    version=models.CharField(max_length=64,blank=True)
    definition=models.TextField(blank=True)
    def __unicode__(self):
       return self.name
    class Meta:
        abstract=True
        ordering=('name',)
        
class Vocab(BaseTerm):
    ''' Holds a vocabulary '''
    uri=models.CharField(max_length=64)
    url=models.CharField(max_length=128,blank=True,null=True)
    def recache(self,update=None):
        '''Obtain a new version from a remote url or the argument and load into database cache'''
        pass
    
class Term(BaseTerm):
    ''' Vocabulary Values, loaded by script, never prompted for via the questionairre '''
    vocab=models.ForeignKey('Vocab') 
        
        
class Reference(models.Model):
    ''' An academic Reference '''
    name=models.CharField(max_length=24)
    citation=models.TextField(blank=True)
    link=models.URLField(blank=True,null=True)
    refTypes=models.ForeignKey('Vocab',null=True,blank=True,editable=False)
    refType=models.ForeignKey('Term')
    centre=models.ForeignKey('Centre',blank=True,null=True)
    def __unicode__(self):
        return self.name
    def delete(self,*args,**kwargs):
        soft_delete(self,*args,**kwargs)
    class Meta:
        ordering=['name','citation']
    
class Component(Doc):
    ''' A model component '''
    # this is the vocabulary NAME of this component:
    scienceType=models.SlugField(max_length=64,blank=True,null=True)
    
    # these next four are to support the questionnaire function
    implemented=models.BooleanField(default=1)
    visited=models.BooleanField(default=0)
    controlled=models.BooleanField(default=0)
    
    model=models.ForeignKey('self',blank=True,null=True,related_name="parent_model")
    realm=models.ForeignKey('self',blank=True,null=True,related_name="parent_realm")
    isRealm=models.BooleanField(default=False)
    isModel=models.BooleanField(default=False)
    
    #to support paramgroups dressed as components
    isParamGroup=models.BooleanField(default=False)
    
    # the following are common parameters
    geneology=models.TextField(blank=True,null=True)
    yearReleased=models.IntegerField(blank=True,null=True)
    otherVersion=models.CharField(max_length=128,blank=True,null=True)
    references=models.ManyToManyField(Reference,blank=True,null=True)
    
    # direct children components:
    components=models.ManyToManyField('self',blank=True,null=True,symmetrical=False)
    paramGroup=models.ManyToManyField('ParamGroup')
    grid=models.ForeignKey('Grid',blank=True,null=True)
    
    isDeleted=models.BooleanField(default=False)

    def copy(self,centre,model=None,realm=None):
        ''' Carry out a deep copy of a model '''
        # currently don't copys here ...
        if centre.__class__!=Centre:
            raise ValueError('Invalid centre passed to component copy')
        
        attrs=['title','abbrev','description',
               'scienceType','controlled','isRealm','isModel','isParamGroup',
               'author','contact','funder']
        kwargs={}
        for i in attrs: kwargs[i]=self.__getattribute__(i)
        if kwargs['isModel']: 
            kwargs['title']=kwargs['title']+' dup'
            kwargs['abbrev']=kwargs['abbrev']+' dup'
        kwargs['uri']=atomuri()
        kwargs['centre']=centre
        
        new=Component(**kwargs)
        new.save() # we want an id, even though we might have one already ... 
        #if new.isModel: print '2',new.couplinggroup_set.all()
       
        # now handle the references
        for r in self.references.all().order_by('id'):
            new.references.add(r)
       
        if model is None:
            if self.isModel:
                model=new
            else:
                raise ValueError('Deep copy called with invalid model arguments: %s'%self)
        elif realm is None:
            if self.isRealm:
                realm=new
            else:
                raise ValueError('Deep copy called with invalid realm arguments: %s'%self)
        new.model=model
        new.realm=realm
       
        for c in self.components.all().order_by('id'):
            logging.debug('About to add a sub-component to component %s (in centre %s, model %s with realm %s)'%(new,centre, model,realm))
            r=c.copy(centre,model=model,realm=realm)
            new.components.add(r)
            logging.debug('Added new component %s to component %s (in centre %s, model %s with realm %s)'%(r,new,centre, model,realm))
            
        for p in self.paramGroup.all().order_by('id'): 
            new.paramGroup.add(p.copy())
        
        ### And deal with the component inputs too ..
        inputset=ComponentInput.objects.filter(owner=self).order_by('id')
        for i in inputset: i.makeNewCopy(new)
        new.save()        
        return new
    
    def couplings(self,simulation=None):
        ''' Return a coupling set for me, in a simulation or not '''
        if not self.isModel:
            raise ValueError('No couplings for non "Model" components')
        mygroups=self.couplinggroup_set.all().order_by('id')
        if len(mygroups):
            cg=mygroups.get(simulation=simulation)
            return Coupling.objects.filter(parent=cg).order_by('id')
        else: return []
        
    def save(self,*args,**kwargs):
        ''' Create a coupling group on first save '''
        cgload=0
        if self.isModel and self.id is None: cgload=1
        Doc.save(self,*args,**kwargs)
        if cgload:
            cg=CouplingGroup(component=self)
            cg.save() 
        
    def filterdown(self):
        ''' To filter responsible party details downwards to subcomponents '''
        for x in self.components.all().order_by('id'):
            x.funder_id=self.funder_id
            x.contact_id=self.contact_id
            x.author_id=self.author_id
            if x.components:
                x.filterdown()
            x.save()  
            
    def filterdowngrid(self):
        ''' To filter grid details downwards to subcomponents '''
        for x in self.components.all().order_by('id'):
            x.grid_id=self.grid_id
            if x.components:
                x.filterdowngrid()
            x.save()         
            
    
class ComponentInput(models.Model):
    ''' This class is used to capture the inputs required by a component '''
    abbrev=models.CharField(max_length=24)
    description=models.TextField(blank=True,null=True)
    #mainly we're going to be interested in boundary condition inputs:
    ctype=models.ForeignKey('Term')
    #the component which owns this input (might bubble up from below realm)
    owner=models.ForeignKey(Component,related_name="input_owner")
    #strictly we don't need this, we should be able to get it by parsing
    #the owners for their parent realms, but it's stored when we create
    #it to improve performance:
    realm=models.ForeignKey(Component,related_name="input_realm")
    #constraint=models.ForeignKey('Constraint',null=True,blank=True)
    cfname=models.ForeignKey('Term',blank=True,null=True,related_name='input_cfname')
    units=models.CharField(max_length=64,blank=True)
    
    def __unicode__(self):
        return '%s (%s)'%(self.abbrev, self.owner)
    def makeNewCopy(self,component):
        new=ComponentInput(abbrev=self.abbrev,description=self.description,ctype=self.ctype,
                           owner=component,realm=component.realm,
                           cfname=self.cfname,units=self.units)
        new.save()
        # if we've made a new input, we need a new coupling
        cg=CouplingGroup.objects.filter(simulation=None).get(component=component.model)
        ci=Coupling(parent=cg,targetInput=new)
        ci.save()
    class Meta:
        ordering=['abbrev']

class Platform(Doc):
    ''' Hardware platform on which simulation was run '''
    compilerVersion=models.CharField(max_length=32)
    maxProcessors=models.IntegerField(null=True,blank=True)
    coresPerProcessor=models.IntegerField(null=True,blank=True)
    hardware=models.ForeignKey('Term',related_name='hardwareVal',null=True,blank=True)
    vendor=models.ForeignKey('Term',related_name='vendorVal',null=True,blank=True)
    compiler=models.ForeignKey('Term',related_name='compilerVal',null=True,blank=True)
    operatingSystem=models.ForeignKey('Term',related_name='operatingSystemVal',null=True,blank=True)
    processor=models.ForeignKey('Term',related_name='processorVal',null=True,blank=True)
    interconnect=models.ForeignKey('Term',related_name='interconnectVal',null=True,blank=True)
    isDeleted=models.BooleanField(default=False)
    #see http://metaforclimate.eu/trac/wiki/tickets/280

def Calendar(elem):
    ''' Retrieve a calendar term and add a toXML instance method. Behaves like a subclass of Term '''
    def toXML(self,parent='calendar'):
        e=ET.Element(parent)
        e.text=self.name
        return e
    cv=Term.objects.filter(vocab=Vocab.objects.get(name='CalendarTypes')).order_by('id')
    try:
        tag=elem[0].tag.split('}')[1]
        r=cv.get(name=tag)
    except Exception,e:
        raise ValueError('Invalid calendar type "%s" (%s)'%(elem.tag,e))
    f=types.MethodType(toXML,r,Term)
    r.toXML=f
    return r

class Experiment(Doc):
    ''' A CMIP5 ***Numerical*** Experiment '''
    rationale=models.TextField(blank=True,null=True)
    requirements=models.ManyToManyField('GenericNumericalRequirement',blank=True,null=True)
    requiredDuration=DateRangeField(blank=True,null=True)
    requiredCalendar=models.ForeignKey('Term',blank=True,null=True,related_name='experiment_calendar')
    #used to identify groups of experiments
    memberOf=models.ForeignKey('Experiment',blank=True,null=True)
    requirementSet=models.ForeignKey('RequirementSet',blank=True,null=True,related_name='ensembleRequirements')
    def __unicode__(self):
        return self.abbrev
   
    @staticmethod   
    def fromXML(filename):
        '''Experiments are defined in XML files, so need to be loaded into django, and
        a copy loaded into the document database as well '''
        
        E=Experiment()
       
        etree=ET.parse(filename)
        txt=open(filename,'r').read()
        logging.debug('Parsing experiment filename %s'%filename)
        root=etree.getroot()
        getter=etTxt(root)
        #basic document stuff, note q'naire doc not identical to experiment bits ...
        doc={'description':'description','shortName':'abbrev','longName':'title','rationale':'rationale'}
        for key in doc:
            E.__setattr__(doc[key],getter.get(root,key))

        # load the calendar type
        calendarName=root.find("{%s}calendar"%cimv)[0].tag.split('}')[1]
        vocab=Vocab.objects.get(name="CalendarTypes")
        term=Term(vocab=vocab,name=calendarName)
        term.save()
        E.requiredCalendar=term
       
        # bypass reading all that nasty gmd party stuff ...
        E.metadataMaintainer=ResponsibleParty.fromXML(root.find('{%s}author'%cimv))
        
        # do some quick length checking
        if len(E.abbrev)>25:
            old=E.abbrev
            E.abbrev=old[0:24]
            logging.info('TOOLONG: Truncating abbreviation %s to %s'%(old,E.abbrev))

        E.uri=atomuri()
        E.save()
        
        for r in root.findall('{%s}numericalRequirement'%cimv):
            #pass the constructor me and the element tree element
            n=instantiateNumericalRequirement(E,r)
            if n is not None: # n should only be None for a RequirementSet
                n.save()
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

    def toXML(self,parent='numericalExperiment'):
        expElement=ET.Element(parent)
        if self.rationale: 
            ET.SubElement(expElement,'rationale').text=self.rationale
        # short name is currently a concatenation of the experiment id
        # and the short name so separate these out
        expName,sep,expShortName=self.abbrev.partition(' ')
        assert sep!="", "Error, experiment short name does not conform to format 'id name'"
        if expShortName and expShortName!='' :
            ET.SubElement(expElement,'shortName').text=expShortName
        ''' longName [1] '''
        if self.title and self.title!='' :
            dummy1,dummy2,longName=self.title.partition(' ')
            assert dummy2!="", "Error, experiment long name does not conform to format 'id name'"
            ET.SubElement(expElement,'longName').text=longName
        ''' description [0..1] '''
        if self.description :
            ET.SubElement(expElement,'description').text=self.description
        ''' experimentNumber [0..1] '''
        if expName and expName!='' :
            ET.SubElement(expElement,'experimentNumber').text=expName
        ''' calendar [1] '''
        if self.requiredCalendar :
            calendarElement=ET.SubElement(expElement,'calendar')
            calTypeElement=ET.SubElement(calendarElement,str(self.requiredCalendar.name))
        else :
            assert False, "Error, a calendar must exist"
        ''' numericalRequirement [1..inf] '''
        for reqObject in self.requirements.all():
            expElement.append(reqObject.toXML())
        return expElement
    
def instantiateNumericalRequirement(experiment,elem):
    ''' This provides an interface to return any sort of numerical requirement, given
    an element '''
    typekey='{http://www.w3.org/2001/XMLSchema-instance}type'
    if typekey in elem.attrib.keys():
        ctype=elem.attrib[typekey]
    else: ctype='NumericalRequirement'
    v=Vocab.objects.get(name='NumReqTypes')
    ctypeVals=Term.objects.filter(vocab=v).order_by('id')
    try:
        ctype=ctypeVals.get(name=ctype)
    except:
        raise ValueError('Invalid numerical requirement type [%s]'%ctype)
    if ctype.name in ['NumericalRequirement','InitialCondition','BoundaryCondition']:
        return NumericalRequirement.fromXML(experiment,elem,ctype)
    elif ctype.name=='SpatioTemporalConstraint':
        return SpatioTemporalConstraint.fromXML(experiment,elem,ctype)
    elif ctype.name=='RequirementSet':
        if experiment.requirementSet:
            raise ValueError('Questionnaire only supports one requirement set per expt')
        experiment.requirementSet=RequirementSet.fromXML(experiment,elem,ctype)
        experiment.save()
        return None
    elif ctype.name=='OutputRequirement':
        logging.info('Output Requirements Not Implmented')
    else:
        raise ValueError('%s not yet implemented'%ctype.name)
    
class GenericNumericalRequirement(ParentModel):
    ''' We use this generic base class, since we want to find all
    numeric requirements in one go from experiments '''
    docid=models.CharField(max_length=64)
    description=models.TextField(blank=True,null=True)
    name=models.CharField(max_length=128)
    ctype=models.ForeignKey('Term',blank=True,null=True)
    options=models.ManyToManyField('RequirementOption',blank=True,null=True) 
    def get_parent_model(self):
        return GenericNumericalRequirement
    def __unicode__(self):
        return self.name
    def gfromXML(self,experiment,elem):
        ''' Initialised with an appropriate experiment, and an element tree Element '''
        getter=etTxt(elem)
        self.docid=getter.get(elem,'id')
        for a in ['description','name']:self.__setattr__(a,getter.getN(elem,a))
        for e in elem.findall('{%s}requirementOption'%cimv):
            ro=RequirementOption()
            a = ro.fromXML(e)
            self.options.add(a)
    def toXML(self,parent='numericalRequirement'):
        reqElement=ET.Element(parent)
        assert self.ctype,"Error, requirement must have ctype set"
        mapping={'BoundaryCondition':'boundaryCondition','InitialCondition':'initialCondition','SpatioTemporalConstraint':'spatioTemporalConstraint'}
        typeElement=ET.SubElement(reqElement,mapping[self.ctype.name])
        if self.docid:
            ET.SubElement(typeElement,'id').text=self.docid
        ET.SubElement(typeElement,'name').text=self.name
        ET.SubElement(typeElement,'description').text=self.description
        if mapping[self.ctype.name]=='spatioTemporalConstraint':
            typeElement.append(self.get_child_object().requiredDuration.xml(parent="requiredDuration"))
        for reqOptionObject in self.options.all():
            typeElement.append(reqOptionObject.toXML())
        return reqElement

class RequirementOption(models.Model):
    ''' A numerical requirement option ''' 
    description=models.TextField(blank=True,null=True) 
    name=models.CharField(max_length=128) 
    docid=models.CharField(max_length=64)
    def __unicode__(self):    
        return self.description 
    def fromXML(self,elem):
        getter=etTxt(elem)
        name=getter.get(elem,'name')
        description=getter.get(elem,'description')
        docid=getter.get(elem,'id')
        a = RequirementOption(name=name,description=description,docid=docid)
        a.save()
        return a
    def toXML(self,parent='requirementOption'):
        reqOptionElement=ET.Element(parent)
        if self.docid:
            ET.SubElement(reqOptionElement,'id').text=self.docid
        ET.SubElement(reqOptionElement,'name').text=self.name
        ET.SubElement(reqOptionElement,'description').text=self.description
        return reqOptionElement

    
class NumericalRequirement(GenericNumericalRequirement):
    ''' A Numerical Requirement '''
    @staticmethod
    def fromXML(experiment,elem,ctype):
        ''' Initialised with an appropriate experiment, and an element tree Element. All
        numerical requirements are initialised through this interface '''
        nr=NumericalRequirement(ctype=ctype)
        nr.save()
        nr.gfromXML(experiment,elem)
        nr.save()
        return nr
        
class SpatioTemporalConstraint(GenericNumericalRequirement):
    requiredDuration=DateRangeField(blank=True,null=True)
    spatialResolution=models.ForeignKey('SpatialResolution',blank=True,null=True)
    @staticmethod
    def fromXML(experiment,elem,ctype):
        nr=SpatioTemporalConstraint(ctype=ctype)
        nr.save()
        nr.gfromXML(experiment,elem)
        op=elem.find('{%s}requiredDuration'%cimv)
        if op is not None: nr.requiredDuration=DateRange.fromXML(op)
        op=elem.find('{%s}spatialResolution'%cimv)
        if op is not None:
            raise ValueError('NO CODE TO READ spatialResolution in SpatioTemporalConstraint')
        nr.save()
        return n

class RequirementSet(GenericNumericalRequirement):
    members=models.ManyToManyField(GenericNumericalRequirement,blank=True,null=True,symmetrical=False,related_name='members')
    @staticmethod
    def fromXML(experiment,elem,ctype):
        nr=RequirementSet(ctype=ctype)
        nr.gfromXML(experiment,elem)
        nr.save()
        for r in elem.findall('{%s}numericalRequirement'%cimv):
            #pass the constructor the experiment and the element tree element
            n=instantiateNumericalRequirement(experiment,r)
            if n is None:
                raise ValueError('Cannot embed RequirementSets')
            else:
                n.save()
                nr.members.add(n)
        return nr
    
class OutputRequirement(GenericNumericalRequirement):
    outputFrequency=models.IntegerField(null=True)
    frequencyUnits=models.ForeignKey('Term',blank=True,null=True,
        related_name='out_frequencyUnits')
    outputPeriod=DateRangeField(blank=True,null=True)
    temporalAveraging=models.ForeignKey('TimeAverage',blank=True,null=True)
    def __init__(self,experiment,elem,ctype):
        self.ctype=ctype
        raise ValueError('Code for output requirements has yet to be completed')
        # the code that follows is a hangover from previously and needs rewriting. 
        myvocab={'frequencyUnits':'FreqUnits',
                 'averagingUnits':'FreqUnits',
                 'spatialResolutionUnits':'SpatialResolutionTypes'}
        for a in ['temporalAveraging','outputFrequency']:
            self.__setattr__(a,getTextN(elem,a))
        for a in ['frequencyUnits','averagingUnits','spatialResolution']:
            vv=getTextN(elem,a)
            if vv:
                v=Vocab.objects.get(name=myvocab[a])
                try:
                    val=Term.objects.filter(vocab=v).get(name=vv)
                    self.__setattr__(a,val)
                except:
                    logging.info('Invalid unit %s not found in vocab %s'%(vv,v))
    
    
class SpatialResolution(models.Model):
    '''FIXME: This is currently unused and untested '''
    units=models.ForeignKey('Term',blank=True,null=True,related_name='sr_units')
    value=models.ForeignKey('Term',blank=True,null=True,related_name='sr_value')
    def __unicode__(self):
        return '%s %s'%(value,units)

class TimeAverage(models.Model):
    units=models.ForeignKey('Term')
    period=models.FloatField()
    def __unicode__(self):
        return '%s %s'%(self.period,self.units)
    def toXML(self,parent='TimeAverage'):
        ''' Serialise to XML '''
        e=ET.Element(parent)
        ET.SubElement(e,'period').text=self.period
        ET.SubElement(e,'units').text=self.units
        return e
        
class Simulation(Doc):
    ''' A CMIP5 Simulation '''
    # models may be used for multiple simulations
    # note that we don't need dates, we can those from the data output, assuming
    # data is output for the entire duration. FIXME: might not have access to
    # that information for all of CMIP5. 
    numericalModel=models.ForeignKey(Component)
    ensembleMembers=models.PositiveIntegerField(default=1)
    #each simulation corresponds to one experiment 
    experiment=models.ForeignKey(Experiment)
    #platforms
    platform=models.ForeignKey(Platform)
   
    # following will be used to construct the DOI
    authorList=models.TextField()
    
    # allow some minor mods to match the criteria, how else would it be described?
    codeMod=models.ManyToManyField('CodeMod',blank=True,null=True)
    
    # this next is here in case we need it later, but I think we shouldn't
    inputMod=models.ManyToManyField('InputMod',blank=True,null=True)
    
    # the following to support relationships to ourselves
    relatedSimulations=models.ManyToManyField('self',through='SimRelationship',symmetrical=False,blank=True,null=True)
    
    duration=DateRangeField(blank=True,null=True)
    
    # mimicking the drs member of ensembleMember for the case of a non-ensemble simulation 
    drsMember=models.CharField(max_length=20,blank=True,null=True)
    
    # not yet used:
    drsOutput=models.ManyToManyField('DRSOutput')
    
    # To mark a simulation as deleting without actually removing it from the database
    isDeleted=models.BooleanField(default=False)
        
    # I/O datasets
    # only modified by resetIO and updateIO
    # the idea being that these are convenience bundles of *files* to create *dataset* which can
    # be represented as *CIM dataobjects* and which couplings can point into ...
    # So, the xml seraialisation will have to take an external closure, work out which datasett it 
    # appears in, and point to the file within it via an xpath expression which uses the dataset uri
    # and a pointer to the file described within it and then the variable with that.
    # But this way we have a sensible number of datasets associatd with a simulation:
    #   - the input data, the ancillary data, the boundary conditoins, and (eventually) the
    #     actual output. The first three of these should appear in the atom feed. # FIXME
    #   - and if it's an ensemble, we may have another two of these associated with
    #     each ensemble member (one output and one input change). However, these ensemble 
    #     datasets are *NOT* pointed to here, you will need to get to those via the ensemble 
    #     member's inputmod.
    datasets=models.ManyToManyField('Dataset')    
    
    def copy(self,experiment):
        ''' Copy this simulation into a new experiment '''
        s=Simulation(abbrev=self.abbrev+' dup',title='copy', 
                     contact=self.contact, author=self.author, funder=self.funder,
                     description=self.description, authorList=self.authorList,
                     uri=atomuri(),
                     experiment=experiment,numericalModel=self.numericalModel,
                     ensembleMembers=1, platform=self.platform, centre=self.centre)
        s.save()
        #now we need to get all the other stuff related to this simulation
        # every simulation has it's own date range:
        s.duration=self.duration.copy()
        for mm in self.inputMod.all().order_by('id'):s.inputMod.add(mm)
        for mm in self.codeMod.all().order_by('id'):s.codeMod.add(mm)
        s._resetIO()
        s.save() # I don't think I need to do this ... but to be sure ...
        #couplings:
        myCouplings=CouplingGroup.objects.filter(component=self.numericalModel).filter(simulation=self).order_by('id')
        for m in myCouplings:
            r=m.duplicate4sim(s)
        # conformance:
        # we can't duplicate that, since we don't know the conformance are the same unless we 
        # have a mapping page somewhere ... so we reset
        s.resetConformances()
        return s
    
    def resetConformances(self):
        ''' We need to set up the conformances or reset them from time to time '''
        existingConformances=Conformance.objects.filter(simulation=self).order_by('id')
        for c in existingConformances:c.delete()
        ctypes=Vocab.objects.get(name='ConformanceTypes')
        defaultConformance=None#Value.objects.filter(vocab=ctypes).get(value='Via Inputs')
        reqs=self.experiment.requirements.all().order_by('id')
        for r in reqs:
            c=Conformance(requirement=r,simulation=self, ctype=defaultConformance)
            c.save()
            
    def updateCoupling(self):
        ''' Update my couplings, in case the user has added some inputs (and hence couplings)
        in the numerical model, but note that updates to existing input couplings in
        numerical models are not propagated to the simuations already made with them. '''
        # first, do we have our own coupling group yet?
        cgs=self.couplinggroup_set.all().order_by('id')
        if len(cgs):
            # we've already got a coupling group, let's update it
            assert len(cgs)==1,'Simulation %s should only have one coupling group'%self
            cgs=cgs[0]
            modelCouplings=self.numericalModel.couplings()
            myCouplings=self.numericalModel.couplings(self)
            myOriginals=[i.original for i in myCouplings]
            logging.debug('Existing Couplings: %s'%myCouplings)
            for m in modelCouplings:
                if m not in myOriginals: 
                    r=m.copy(cgs)
        else:
            # get the model coupling group ... and copy it.
            # it's possible we might be doing this before there is a modelling group
            mcgs=self.numericalModel.couplinggroup_set.all().order_by('id')
            if len(mcgs)==0: 
                pass # nothing to do
                cgs=None # I'm not sure this should ever happen any more ...
            else:
                cgs=mcgs.get(simulation=None)
                cgs=cgs.duplicate4sim(self)
        # having updated the couplings, we'll now find any new files (if any)
        logging.debug('Updated couplings: %s'%self.numericalModel.couplings(self))
        self._updateIO()
        return cgs  # it's quite useful to get this back (e.g. for resetclosures etc)

    def resetCoupling(self,closures=False):
        '''We had some couplings, but we need to get rid of them for some reason
        (usually because we've just changed model) '''
        self._resetIO()
        cgs=self.couplinggroup_set.all().order_by('id')
        if len(cgs)<>0:
            assert len(cgs)==1,'Expect only one coupling group for simulation %s'%self
            cg=cgs[0]
            cg.delete()
        # now put back the ones from the model
        cg=self.updateCoupling()
        if closures:cg.propagateClosures()
        
    def _resetIO(self):
        ''' create or replace the default datasets for this simulation, usually to be
        called by resetCoupling '''
        # see updateIO for documentation of what we're doing here.
        itypes=Term.objects.filter(vocab=Vocab.objects.get(name='InputTypes')).order_by('id')
        existing=self.datasets.all().order_by('id')
        for e in existing:e.delete4real()
        for itype in itypes:
            d=Dataset(usage=itype)
            d.save()
            self.datasets.add(d)
            
    def _updateIO(self):
        ''' To be called as an aid for serialisation for display, checks
        the external closures associated with each input type and aggregates
        the files into the datasets associated with this simulation. We
        expect this to be called after a simulation has updated couplings'''
        # first get the list of input types (so these'll be the datasets):
        itypes=Term.objects.filter(vocab=Vocab.objects.get(name='InputTypes')).order_by('id')
        # now these are my datasets corresponding to those types (we hope):
        existing=self.datasets.all().order_by('id')
        assert len(existing)==len(itypes),'Unexpected condition (%s,%s)on entry to simulation method updateIO for %s'%(len(existing),len(itypes),self)
        # all my couplings:
        myCouplings=self.numericalModel.couplings(self)
        for itype in itypes:
            # one dataset at a time
            d=existing.get(usage=itype)
            # now restrict our external closures to just those relevant to this dataset
            # we want couplings that are to target inputs which (themselves componentinputs)
            # have attribute ctype equal to itype.
            theseCouplings=myCouplings.filter(targetInput__ctype=itype).order_by('id')
            # now get all the external closures in my couplings (aka files)
            # avoid an extra database query to get to the files ...
            ecset=ExternalClosure.objects.select_related('targetFile').filter(coupling__in=theseCouplings).order_by('id')
            for e in ecset:
                if e.targetFile not in d.children.all().order_by('id'): d.children.add(e.targetFile)
                
class PhysicalProperty(Term):
    units=models.ForeignKey(Term,related_name='property_units')

class ParamGroup(models.Model):
    ''' This holds either constraintGroups or parameters to link to components '''
    name=models.CharField(max_length=64,default="Attributes")
    paramgroups=models.ManyToManyField('self',blank=True,null=True,symmetrical=False)
    
    def copy(self):
        new=ParamGroup(name=self.name)
        new.save()
        for constraint in self.constraintgroup_set.all().order_by('id'):constraint.copy(new)
        return new
    def __unicode__(self):
        return self.name

class ConstraintGroup(models.Model):
    constraint=models.CharField(max_length=256,blank=True,null=True)
    parentGroup=models.ForeignKey(ParamGroup)
    def __unicode__(self):
        if self.constraint: 
            return self.constraint
        else: return '' 
    def copy(self,paramgrp):
        new=ConstraintGroup(constraint=self.constraint,parentGroup=paramgrp)
        new.save()
        for param in self.baseparam_set.all().order_by('id'): param.copy(new)
        
class BaseParam(ParentModel):
    ''' Base class for parameters within constraint groups '''
    # We can't the name of this is a value in vocab, because it might be user generated '''
    name=models.CharField(max_length=64,blank=False)
    # lives in 
    constraint=models.ForeignKey(ConstraintGroup)
    #strictly we don't need the following attribute, but it simplifies template code
    controlled=models.BooleanField(default=False)
    # should have definition
    definition=models.CharField(max_length=1024,null=True,blank=True)
    #
    def get_parent_model(self):
        return BaseParam
    # The rest to allow copying of base and subclasses
    def copy(self,constraint):
        obj=self.get_child_object()
        attr=['name','controlled','definition','controlled']+obj.cpattr()
        d={}
        for a in attr: d[a]=obj.__getattribute__(a)
        d['constraint']=constraint
        o=obj.__class__(**d)
        o.save()
        if self.get_child_name()=='orparam':
            for m in obj.value.all().order_by('id'): o.value.add(m)
        return o
        
class OrParam(BaseParam):
    value=models.ManyToManyField(Term)
    vocab=models.ForeignKey(Vocab,blank=True,null=True)
    def __unicode__(self):
        s='%s:'%self.name+','.join([a for a in self.value.all().order_by('id')])
        return s
    def cpattr(self):
        return ['vocab']

class XorParam(BaseParam):
    value=models.ForeignKey(Term,blank=True,null=True)
    vocab=models.ForeignKey(Vocab,blank=True,null=True)
    def __unicode__(self):
        s='%s:%s'%(self.name,self.value)
        return s
    def cpattr(self):
        return ['value','vocab']

class KeyBoardParam(BaseParam):
    value=models.CharField(max_length=1024,blank=True,null=True)
    # but it might be a numeric parameter, in which case we have more attributes
    units=models.CharField(max_length=1024,null=True,blank=True)
    numeric=models.BooleanField(default=False)
    def __unicode__(self):
        s='%s:%s'%(self.name,self.value)
        if self.numeric and self.units: s+='(%s)'%self.units
        return s
    def cpattr(self):
        return ['value','units','numeric']


class DataContainer(Doc):
    ''' This holds multiple data objects. Some might think of this as a file '''
    # a name for drop down file lists (and yes it's short)
    # use the doc abbrev for the drop down file lists
    # use the doc title as a real name for disambiguation, although the link is authorative 
    # use the doc description to tell us what's in the container.
    # use the doc centre and owner stuff ...
    # a link to the object if possible:
    link=models.URLField(blank=True)
    # container format
    format=models.ForeignKey('Term',blank=True,null=True) 
    # references (including web pages)
    reference=models.ForeignKey(Reference,blank=True,null=True)
    #experiment relationships used to help close down the number of files shown ...
    experiments=models.ManyToManyField(Experiment,blank=True,null=True)
    def __unicode__(self):
        if self.abbrev <> '':
            return self.abbrev
        else: return self.title[0:44]  # truncation ...
    class Meta:
        ordering=('centre','title')
            
class DataObject(models.Model):
    ''' Holds a variable within a data container '''
    container=models.ForeignKey(DataContainer)
    description=models.TextField()
    # if the data object is a variable within a dataset at the target uri, give the variable
    variable=models.CharField(max_length=128,blank=True)
    # and if possible the CF name
    cfname=models.ForeignKey('Term',blank=True,null=True,related_name='data_cfname')
    # references (including web pages)
    reference=models.ForeignKey(Reference,blank=True,null=True)
    # not using this at the moment, but keep for later: csml/science type
    featureType=models.ForeignKey('Term',blank=True,null=True)
    # not using this at the moment, but keep for later:
    drsAddress=models.CharField(max_length=256,blank=True)
    def __unicode__(self): return self.variable
    class Meta:
        ordering=('variable',)
    
class Dataset(Doc):
    ''' Used to aggregate data containers together in the questionnaire.
    It's a convenience class, not a full map into a CIM dataset '''
    # Expect to use this to aggregate the various files needed by a 
    # simulation into the number of datasets 
    children=models.ManyToManyField(DataContainer)
    # The following is not serialised, but helps discriminate internal to the questionnaire
    usage=models.ForeignKey(Term)
    # Either the dataset is associated with a simulation or an EnsembleMember, but
    # they know that, the dataset is agnostic
    def __unicode__(self): 
        return '%s(%s)'%(self.usage,len(self.children.all().order_by('id')))

class CouplingGroup(models.Model):
    ''' This class is used to help manage the couplings in terms of presentation and
    their copying between simulations '''
    # parent component, must be a model for CMIP5:
    component=models.ForeignKey(Component)
    # may also be associated with a simulation, in which case there is an original
    simulation=models.ForeignKey(Simulation,blank=True,null=True)
    original=models.ForeignKey('CouplingGroup',blank=True,null=True)
    # to limit the size of drop down lists, we have a list of associated files
    associatedFiles=models.ManyToManyField(DataContainer,blank=True,null=True)
    def duplicate4sim(self,simulation):
        '''Make a copy of self, and associate with a simulation'''
        # first make a copy of self
        args=['component',]
        kw={'original':self,'simulation':simulation}
        for a in args:kw[a]=self.__getattribute__(a)
        new=CouplingGroup(**kw)
        new.save()
        #can't do the many to manager above, need to do them one by one
        for af in self.associatedFiles.all().order_by('id'):new.associatedFiles.add(af)
        # now copy all the individual couplings associated with this group
        cset=self.coupling_set.all().order_by('id')
        for c in cset: c.copy(new)
        return new
    def propagateClosures(self):
        ''' This is a one stop shop to update all the closures from an original source
        model coupling group to a simulation coupling group '''
        if self.original is None:raise ValueError('No original coupling group available')
        #start by finding all the couplings in this coupling set.
        myset=self.coupling_set.all().order_by('id')
        for coupling in myset:
            # find all the relevant closures and copy them
            coupling.propagateClosures()          
        return '%s couplings updated '%len(myset)
    class Meta:
        ordering=['component']
    def __unicode__(self):
        return 'Coupling Group for %s (simulation %s)'%(self.component,self.simulation)

class Coupling(models.Model):
    # parent coupling group
    parent=models.ForeignKey(CouplingGroup)
    # coupling for:
    targetInput=models.ForeignKey(ComponentInput)
    # coupling details (common to all closures)
    inputTechnique=models.ForeignKey('Term',related_name='%(class)s_InputTechnique',blank=True,null=True)
    FreqUnits=models.ForeignKey('Term',related_name='%(class)s_FreqUnits',blank=True,null=True)
    couplingFreq=models.IntegerField(blank=True,null=True)
    manipulation=models.TextField(blank=True,null=True)
    # original if I'm a copy.
    original=models.ForeignKey('Coupling',blank=True,null=True)
    notInUse=models.BooleanField(default=False)
    
    def __unicode__(self):
        if self.parent.simulation:
            return 'CouplingFor:%s(in %s)'%(self.targetInput,self.parent.simulation)
        else:
            return 'CouplingFor:%s'%self.targetInput
    def copy(self,group):
        '''Make a copy of self, and associate with a new group'''
        # first make a copy of self
        args=['inputTechnique','couplingFreq','FreqUnits','manipulation','targetInput']
        if self.original:
            kw={'original':self.original}
        else: kw={'original':self}
        kw['parent']=group
        for a in args:kw[a]=self.__getattribute__(a)
        new=Coupling(**kw)
        new.save()
        # We don't copy all the individual closures by default. Currently we
        # imagine that can happen in two ways but both are under user control.
        # Either they to it individually, or they do it one by one.
        return new
    def propagateClosures(self):
        ''' Update my closures from an original if it exists '''
        if self.original is None:raise ValueError('No original coupling available')
        for cmodel in [InternalClosure,ExternalClosure]:
            set=cmodel.objects.filter(coupling=self.original).order_by('id')
            for i in set: i.makeNewCopy(self)
        return '%s updated from %s'%(self,self.original)
    class Meta:
        ordering=['targetInput']
    
class CouplingClosure(models.Model):
    ''' Handles a specific closure to a component '''
    # we don't need a closed attribute, since the absence of a target means it's open.
    coupling=models.ForeignKey(Coupling,blank=True,null=True)
    #http://docs.djangoproject.com/en/dev/topics/db/models/#be-careful-with-related-name
    spatialRegrid=models.ForeignKey('Term',related_name='%(class)s_SpatialRegrid')
    temporalTransform=models.ForeignKey('Term',related_name='%(class)s_TemporalTransform')
    class Meta:
        abstract=True
   

class InternalClosure(CouplingClosure): 
    target=models.ForeignKey(Component,blank=True,null=True)
    ctype='internal'
    def __unicode__(self):
        return 'iClosure %s'%self.target
    def makeNewCopy(self,coupling):
        ''' Copy closure to a new coupling '''
        kw={'coupling':coupling}
        for key in ['spatialRegrid','temporalTransform','target']:
            kw[key]=self.__getattribute__(key)
        new=self.__class__(**kw)
        new.save()
    
class ExternalClosure(CouplingClosure):
    ''' AKA boundary condition '''
    target=models.ForeignKey(DataObject,blank=True,null=True)
    targetFile=models.ForeignKey(DataContainer,blank=True,null=True)
    ctype='external'
    def __unicode__(self):
        return 'eClosure %s'%self.target    
    def makeNewCopy(self,coupling):
        ''' Copy closure to a new coupling '''
        kw={'coupling':coupling}
        for key in ['spatialRegrid','temporalTransform','target','targetFile']:
            kw[key]=self.__getattribute__(key)
        new=self.__class__(**kw)
        new.save()

class EnsembleDoc(Doc):
    ''' This class is only used to create an ensemble doc by the makeDoc method of an Ensemble '''
    # we have both classes as a hack to avoid problems saving forms and because the ensemble
    # properties mostly come from the simulation.
    etype=models.ForeignKey(Term,blank=True,null=True)

class Ensemble(models.Model):
    description=models.TextField(blank=True,null=True)
    etype=models.ForeignKey(Term,blank=True,null=True)
    simulation=models.ForeignKey(Simulation)
    doc=models.ForeignKey(EnsembleDoc,blank=True,null=True)
    def updateMembers(self):
        ''' Make sure we have enough members, this needs to be called if the
        simulation changes it's mind over the number of members '''
        objects=self.ensemblemember_set.all().order_by('id')
        n=len(objects)
        nShouldBe=self.simulation.ensembleMembers
        ndif=n-nShouldBe
        for i in range(abs(ndif)): 
            if ndif >0:
                objects[n-1-i].delete()
            elif ndif < 0:
                e=EnsembleMember(ensemble=self,memberNumber=n+i+1)
                e.save()
    def makeDoc(self):
        ''' Returns an EnsembleDoc instance of self, which can be used to validate etc '''
        if self.doc: 
            # I don't believe it's possible for the ensemble to be associated with a different simulation
            # since last time we came.
            ed=self.doc
        else: 
            ed=EnsembleDoc(uri=atomuri())
        ed.etype=self.etype
        # we can't assume that none of the simulation characteristics have not been changed, so
        # let's just copy them lock stock and barrel.
        for a in ('centre','author','funder','contact','metadataMaintainer','title','abbrev','description'):
            ed.__setattr__(a,self.simulation.__getattribute__(a))
        # is that enough of a shell?
        ed.save()
        if not self.doc :
            self.doc=ed
            self.save()
        return ed
    
class EnsembleMember(models.Model):
    ensemble=models.ForeignKey(Ensemble,blank=True,null=True)
    memberNumber=models.IntegerField() # realisation
    cmod=models.ForeignKey('CodeMod',blank=True,null=True)
    imod=models.ForeignKey('InputMod',blank=True,null=True)
    drsMember=models.CharField(max_length=10,blank=True,null=True)
    requirement=models.ForeignKey(GenericNumericalRequirement,blank=True,null=True)
    def __unicode__(self):
        return '%s ensemble member %s'%(self.ensemble.simulation,self.memberNumber)
    class Meta:
        ordering=('memberNumber',)
    
    
# Consider an ensemble with a staggered start.
# Consider an ensemble with a range of realisations reflecting different initialisatoin strategies
# Consider a perturbed physics ensemble.
# We also have modifications used to simplify having to enter model after model for minor mod # changes.

class realKVP(models.Model):
    ''' Simply used to hold a key value pair '''
    k=models.CharField(max_length=64,blank=True,null=True)
    v=models.FloatField(blank=True,null=True)

class Modification(ParentModel):
    ''' Base class for all modifications -  note not abstract, so we can get at all modifications
    regardless of their type '''
    mnemonic=models.SlugField()
    description=models.TextField()
    centre=models.ForeignKey(Centre)
    def __unicode__(self):
        return '%s(%s)'%(self.mnemonic,self.get_child_name())
    def get_parent_model(self):
        return Modification
    class Meta:
        ordering=('mnemonic',)
    def delete(self,*args,**kwargs):
        ''' Avoid deleting documents which have foreign keys to this instance'''
        return soft_delete(self,*args,**kwargs)

class CodeMod(Modification):
    '''This is a modification to some code. The description describes what has been done.
    We can imagine that the code mod is either a change to the physics or a component value somewhere '''
    # This is the component which has been modified.
    component=models.ForeignKey(Component)
    # Type of change: parameter change or code change ...
    mtype=models.ForeignKey(Term,blank=True,null=True)
    # Optionally, we might want some real values associated with a named parameter so we can 
    # order some ensemble members (e.g. ClimatePrediction.net wanting to find all the 
    # realisations with a particular value of dropsize). Unfortuantely, they may have
    # perturbed a number of things each time.
    mods=models.ManyToManyField(realKVP)
    # but we only support one for now (so as to make the form handling easier 
    k=models.CharField(max_length=64,blank=True,null=True)
    v=models.FloatField(blank=True,null=True)

class InputMod(Modification):
    ''' There are (currently) three types of inputs, any of which might have been modified to create the 
    ensemble members. In many cases we're interested in changing the date of the data from files, or
    changing the date of the integration itself. So, we have two interesting cases as to what might have 
    been done with the inputs. We might read them from different files, or we might select different
    members of the files. In either case we're probably not interested in redefining all the inputs, 
    but we'd better allow the user to do so if they so wish '''
    inputTypeModified=models.ForeignKey(Term,related_name='usage') # so this keys into the input types vocabulary
    memberStartDate=SimDateTimeField(blank=True,null=True)
    # if the files are not modified then we don't need to describe the changed files.
    # if they are changed, we either change the files, or we create a file modification
    # description ...
    dataset=models.ForeignKey('Dataset',blank=True,null=True)
    # if we've been lazy and this isn't the actual dataset used, then we need to serialise this
    # as a related dataset and not the dataset itself. So we'd need to describe the relationship.
    dataRelationship=models.ForeignKey(Term,related_name='relationship',blank=True,null=True)

class Conformance(models.Model):
    ''' This relates a numerical requirement to an actual solution in the simulation '''
    # the identifier of the numerical requirement:
    requirement=models.ForeignKey(GenericNumericalRequirement)
    # simulation owning the requirement 
    simulation=models.ForeignKey(Simulation)
    # conformance type from the controlled vocabulary
    ctype=models.ForeignKey(Term,blank=True,null=True)
    #
    mod=models.ManyToManyField('Modification',blank=True,null=True)
    coupling=models.ManyToManyField(Coupling,blank=True,null=True)
    option=models.ForeignKey(RequirementOption,blank=True,null=True)
    # notes
    description=models.TextField(blank=True,null=True)
    def __unicode__(self):
        return "%s for %s"%(self.ctype,self.requirement) 
    
class Grid(Doc):
    topGrid=models.ForeignKey('self',blank=True,null=True,related_name="parent_grid")    
    istopGrid=models.BooleanField(default=False)
    
    # direct children components:
    grids=models.ManyToManyField('self',blank=True,null=True,symmetrical=False)
    paramGroup=models.ManyToManyField('ParamGroup')
    references=models.ManyToManyField(Reference,blank=True,null=True)
    isDeleted=models.BooleanField(default=False)
    
    #to support paramgroups dressed as components/grids
    isParamGroup=models.BooleanField(default=False)
    
    
    def copy(self,centre,topGrid=None):
        ''' Carry out a deep copy of a grid '''
        # currently don't copys here ...
        if centre.__class__!=Centre:
            raise ValueError('Invalid centre passed to grid copy')
        
        attrs=['title','abbrev','description',
               'istopGrid','isParamGroup','author','contact','funder']
        kwargs={}
        for i in attrs: kwargs[i]=self.__getattribute__(i)
        if kwargs['istopGrid']: 
            kwargs['title']=kwargs['title']+' dup'
            kwargs['abbrev']=kwargs['abbrev']+' dup'
        kwargs['uri']=atomuri()
        kwargs['centre']=centre
        
        new=Grid(**kwargs)
        new.save() # we want an id, even though we might have one already ... 
        #if new.isModel: print '2',new.couplinggroup_set.all()
       
        if topGrid is None:
            if self.istopGrid:
                topGrid=new
            else:
                raise ValueError('Deep copy called with invalid grid arguments: %s'%self)
        
        new.topGrid=topGrid
       
        for c in self.grids.all().order_by('id'):
            logging.debug('About to add a sub-grid to grid %s (in centre %s, grid %s)'%(new,centre, topGrid))
            r=c.copy(centre,topGrid=topGrid)
            new.grids.add(r)
            logging.debug('Added new grid %s to grid %s (in centre %s, grid %s)'%(r,new,centre, topGrid))
            
        for p in self.paramGroup.all().order_by('id'): 
            new.paramGroup.add(p.copy())
       
        new.save()        
        return new
    
class DRSOutput(models.Model):
    ''' This is a holding class for how a simulation relates to it's output in the DRS '''
    activity=models.CharField(max_length=64)
    product=models.CharField(max_length=64)
    institute=models.ForeignKey(Centre)
    model=models.ForeignKey(Component)
    experiment=models.ForeignKey(Experiment)
    frequency=models.ForeignKey(Term,blank=True,null=True,related_name='drs_frequency')
    realm=models.ForeignKey(Term,related_name='drs_realm')
    # we don't need to point to simulations, they point to this ...
    def __unicode__(self):
        return '%s/%s/%s/%s/%s/%s/%s/'%(activity,product,institute,model,experiment,frequency,realm)


class TestDocs(object):
    ''' Dummy queryset for test documents'''
    @staticmethod
    def getdocs(testdir):
        myfiles=[]
        for f in os.listdir(testdir):
            if f.endswith('.xml'): myfiles.append(TestDocumentSet(testdir,f))
        return TestDocs(myfiles)
    def __init__(self,myfiles):
        self.myfiles=myfiles
    def order_by(self,arg):
        ''' Just return the list, which probably has only one entry '''
        return self.myfiles

class TestDocumentSet(object):
    ''' This class provides pseudo CIMObjects from files on disk '''
    class DummyAuthor(object):
        def __init__(self):
            self.name='Test Author: Gerry Devine'
            self.email='g.devine@met.reading.ac.uk'
    def __init__(self,d,f):
        ff=os.path.join(d,f)
        ef=ET.parse(ff)
        cimns = 'http://www.metaforclimate.eu/schema/cim/1.5'
        cimdoclist=['{%s}modelComponent' %cimns,'{%s}platform' %cimns,'{%s}CIMRecord/{%s}CIMRecord/{%s}simulationRun' %(cimns,cimns,cimns)]
        for cimdoc in cimdoclist:
            if ef.getroot().find(cimdoc) is not None:
                e=ef.getroot().find(cimdoc)
                
        getter=etTxt(e)
        #basic document stuff for feed
        doc={'description':'description','shortName':'abbrev','longName':'title',
             'documentCreationDate':'created','updated':'updated','documentID':'uri'}
        for key in doc.keys():
            self.__setattr__(doc[key],getter.get(e,key))
        self.fname=f
        self.cimtype='DocumentSet'
        self.author=self.DummyAuthor()
        #if self.created=='':self.created=datetime.now()
        #if self.updated=='':self.updated=datetime.now()
        #FIXME: temporary fix for strange date bug
        self.created=datetime.now()
        self.updated=datetime.now()

    def get_absolute_url(self):
        return reverse('cmip5q.protoq.views.testFile',args=(self.fname,))

class DocFeed(Feed):
    ''' This is the atom feed for xml documents available from the questionnaire '''
    # See http://code.google.com/p/django-atompub/wiki/UserGuide
    feeds={'platform':CIMObject.objects.filter(cimtype='platform'),
           'simulation':CIMObject.objects.filter(cimtype='simulation'),
           'component':CIMObject.objects.filter(cimtype='component'),
           'experiment':CIMObject.objects.filter(cimtype='experiment'),
           'files':CIMObject.objects.filter(cimtype='dataContainer'),
           'all':CIMObject.objects.all(),
           'test':TestDocs.getdocs(settings.TESTDIR)}
    def _mydomain(self):
        # the request object has been passed to the constructor for the Feed base class,
        # so we have access to the protocol, port, etc
        current_site = RequestSite(self.request)
        return 'http://%s/'%current_site.domain
    def _myurl(self,model):
        return self._mydomain()+reverse('django.contrib.syndication.views.feed',args=('cmip5/%s'%model,))
    def get_object(self,params):
        ''' Used for parameterised feeds '''
        assert params[0] in self.feeds,'Unknown feed request'
        return params[0]
    def feed_id (self,model):
        return self._myurl(model)
    def feed_title(self,model):
        return 'CMIP5 model %s metadata'%model
    def feed_subtitle(self,model):
        return 'Metafor questionnaire - completed %s documents'%model
    def feed_authors(self,model):
        return [{'name':'The metafor team'}]
    def feed_links(self,model):
        u=self._myurl(model)
        return [{"rel": "self", "href": "%s"%u}]
    def feed_extra_attrs(self,model):
        return {'xml:base':self._mydomain()}
    def items(self,model):
        return self.feeds[model].order_by('-updated')
    def item_id(self,item):
        return 'urn:uuid:%s'%item.uri
    def item_title(self,item):
        return item.title
    def item_authors(self,item):
        if item.author is not None:
            return [{'name': item.author.name,'email':item.author.email}]
        else: return []
    def item_updated(self,item):
        return item.updated
    def item_published(self,item):
        return item.created
    def item_links(self,item):
        return [{'href':item.get_absolute_url(),'rel':'via','type':'application/xml'}]
    def item_summary(self,item):
        if item.description:
            return item.description
        else:
            return '%s:%s'%(item.cimtype,item.title)
    def item_content(self,item):
        ''' Return out of line link to the content'''
        return {"type": "application/xml", "src":item.get_absolute_url()},""

