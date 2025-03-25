from django.db import models
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes import generic
from django import forms
from django.forms.models import modelformset_factory
from django.forms.util import ErrorList
from django.core.urlresolvers import reverse
from django.db.models.query import CollectedObjects, delete_objects
from django.db.models.fields.related import ForeignKey
from lxml import etree as ET

from django.db.models import permalink
from django.core.files import File

from atom import Feed
from cmip5q.protoq.cimHandling import *
from cmip5q.protoq.utilities import atomuri

from django.conf import settings
logging=settings.LOG
from django.core.files.base import ContentFile
from django.db.models.query import QuerySet


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
    else:
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
    abbrev=models.CharField(max_length=32)
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
            return 100.0*(1.0-float(self.validErrors)/self.numberOfValidationChecks)
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
        logging.info('WARNING Exporting document for ESG regardless of validation state')
        valid=True # FIXME
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
    
class Centre(ResponsibleParty):
    ''' A CMIP5 modelling centre '''
    # It's such an important entity it gets it's own sub class ...
    # I wanted to preserve the API, but title will need to change to name
    party=models.OneToOneField(ResponsibleParty,parent_link=True,related_name='party')
    def __init__(self,*args,**kwargs):
        ResponsibleParty.__init__(self,*args,**kwargs)
        
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
    
    # the following are common parameters
    geneology=models.TextField(blank=True,null=True)
    yearReleased=models.IntegerField(blank=True,null=True)
    otherVersion=models.CharField(max_length=128,blank=True,null=True)
    references=models.ManyToManyField(Reference,blank=True,null=True)
    
    # direct children components:
    components=models.ManyToManyField('self',blank=True,null=True,symmetrical=False)
    paramGroup=models.ManyToManyField('ParamGroup')
    grid=models.ForeignKey('Grid',blank=True,null=True)

    def copy(self,centre,model=None,realm=None):
        ''' Carry out a deep copy of a model '''
        # currently don't copys here ...
        if centre.__class__!=Centre:
            raise ValueError('Invalid centre passed to component copy')
        
        attrs=['title','abbrev','description',
               'scienceType','controlled','isRealm','isModel',
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
        for r in self.references.all():
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
       
        for c in self.components.all():
            logging.debug('About to add a sub-component to component %s (in centre %s, model %s with realm %s)'%(new,centre, model,realm))
            r=c.copy(centre,model=model,realm=realm)
            new.components.add(r)
            logging.debug('Added new component %s to component %s (in centre %s, model %s with realm %s)'%(r,new,centre, model,realm))
            
        for p in self.paramGroup.all(): 
            new.paramGroup.add(p.copy())
        
        ### And deal with the component inputs too ..
        inputset=ComponentInput.objects.filter(owner=self)
        for i in inputset: i.makeNewCopy(new)
        new.save()        
        return new
    
    def couplings(self,simulation=None):
        ''' Return a coupling set for me, in a simulation or not '''
        if not self.isModel:
            raise ValueError('No couplings for non "Model" components')
        mygroups=self.couplinggroup_set.all()
        if len(mygroups):
            cg=mygroups.get(simulation=simulation)
            return Coupling.objects.filter(parent=cg)
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
        for x in self.components.all():
            x.funder_id=self.funder_id
            x.contact_id=self.contact_id
            x.author_id=self.author_id
            if x.components:
                x.filterdown()
            x.save()
            
            #q = Component.objects.get(id=x.id)
            #q.author_id=x.author_id
            #q.contact_id=x.contact_id
            #q.funder_id=x.funder_id
            #if q.components:
            #    q.filterdown()
            #q.save()           
            
    
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
    #see http://metaforclimate.eu/trac/wiki/tickets/280

    
    
class ClosedDateRange(models.Model):
    ''' Actually this is a DateRange as well '''
    startDate=models.CharField(max_length=32,blank=True,null=True)
    calendar=models.ForeignKey('Term',blank=True,null=True,related_name='date_calendar')
    description=models.TextField() # occasionally it's too hard to fix it.
    endDate=models.CharField(max_length=32,blank=True,null=True)
    length=models.FloatField(blank=True,null=True)  # years
    lengthUnits=models.ForeignKey('Term',blank=True,null=True,related_name='date_lengthunits')
    def __unicode__(self):
        d=''
        if self.description:
            d='%s: '%self.description
        if self.startDate:
            d+=self.startDate
        if self.endDate:
            return d+' to %s (%s%s)'%(self.endDate,self.length,self.lengthUnits)
        else:
            return d+' onwards'
    def copy(self):
        d={}
        for a in ['startDate','calendar','description','endDate','length','lengthUnits']:
            d[a]=self.__getattribute__(a)
        new=ClosedDateRange(**d)
        new.save()
        return new

class Experiment(Doc):
    ''' A CMIP5 Numerical Experiment '''
    rationale=models.TextField(blank=True,null=True)
    requirements=models.ManyToManyField('NumericalRequirement',blank=True,null=True)
    requiredDuration=models.ForeignKey(ClosedDateRange,blank=True,null=True)
    requiredCalendar=models.ForeignKey('Term',blank=True,null=True,related_name='experiment_calendar')
    #used to identify groups of experiments
    memberOf=models.ForeignKey('Experiment',blank=True,null=True)
    def __unicode__(self):
        return self.abbrev

class NumericalRequirement(models.Model):
    ''' A numerical Requirement '''
    docid=models.CharField(max_length=64)
    description=models.TextField(blank=True,null=True)
    name=models.CharField(max_length=128)
    ctype=models.ForeignKey('Term',blank=True,null=True)
    consistsOf=models.ManyToManyField('self',blank=True,null=True,symmetrical=False)
    def __unicode__(self):
        return self.name
    
class SpatioTemporalConstraint(NumericalRequirement):
    frequencyUnits=models.ForeignKey('Term',blank=True,null=True,
        related_name='stc_frequencyUnits')
    outputFrequency=models.IntegerField(null=True)
    spatialResolution=models.ForeignKey('Term',blank=True,null=True,
        related_name='stc_spatialRes')
    averagingUnits=models.ForeignKey('Term',blank=True,null=True,
        related_name='stc_averagingUnits')
    temporalAveraging=models.IntegerField(null=True)
    outputPeriod=models.ForeignKey(ClosedDateRange,blank=True,null=True)

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
    modelMod=models.ManyToManyField('ModelMod',blank=True,null=True)
    
    # this next is here in case we need it later, but I think we shouldn't
    inputMod=models.ManyToManyField('InputMod',blank=True,null=True)
    
    # the following to support relationships to ourselves
    relatedSimulations=models.ManyToManyField('self',through='SimRelationship',symmetrical=False,blank=True,null=True)
    
    duration=models.ForeignKey('ClosedDateRange',blank=True,null=True)
    
    # not yet used:
    drsOutput=models.ManyToManyField('DRSOutput')
        
    def updateCoupling(self):
        ''' Update my couplings, in case the user has added some inputs (and hence couplings)
        in the numerical model, but note that updates to existing input couplings in
        numerical models are not propagated to the simuations already made with them. '''
        # first, do we have our own coupling group yet?
        cgs=self.couplinggroup_set.all()
        if len(cgs): 
            # we've already got a coupling group, let's update it
            assert(len(cgs)==1,'Simulation %s should only have one coupling group'%self) 
            cgs=cgs[0]
            modelCouplings=self.numericalModel.couplings()
            myCouplings=self.numericalModel.couplings(self)
            myOriginals=[i.original for i in myCouplings]
            for m in modelCouplings:
                if m not in myOriginals: 
                    r=m.copy(cgs)
        else:
            # get the model coupling group ... and copy it.
            # it's possible we might be doing this before there is a modelling group
            mcgs=self.numericalModel.couplinggroup_set.all()
            if len(mcgs)==0: 
                pass # nothing to do
                cgs=None # I'm not sure this should ever happen any more ...
            else:
                cgs=mcgs.get(simulation=None)
                cgs=cgs.duplicate4sim(self)
        return cgs  # it's quite useful to get this back (e.g. for resetclosures etc)

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
        for mm in self.inputMod.all():s.inputMod.add(mm)
        for mm in self.modelMod.all():s.modelMod.add(mm)
        s.save() # I don't think I need to do this ... but to be sure ...
        #couplings:
        myCouplings=CouplingGroup.objects.filter(component=self.numericalModel).filter(simulation=self)
        for m in myCouplings:
            r=m.duplicate4sim(s)
        # conformance:
        # we can't duplicate that, since we don't know the conformance are the same unless we 
        # have a mapping page somewhere ... so we reset
        s.resetConformances()
        return s
        
    def resetConformances(self):
        # we need to set up the conformances or reset them.
        existingConformances=Conformance.objects.filter(simulation=self)
        for c in existingConformances:c.delete()
        ctypes=Vocab.objects.get(name='ConformanceTypes')
        defaultConformance=None#Value.objects.filter(vocab=ctypes).get(value='Via Inputs')
        reqs=self.experiment.requirements.all()
        for r in reqs:
            c=Conformance(requirement=r,simulation=self, ctype=defaultConformance)
            c.save()
    
    def resetCoupling(self,closures=False):
        # we had some couplings, but we need to get rid of them for some reason
        # (usually because we've just change model)
        cgs=self.couplinggroup_set.all()
        if len(cgs)<>0:
            assert(len(cgs)==1,'Expect only one coupling group for simulation %s'%self)
            cg=cgs[0]
            cg.delete()
        # now put back the ones from the model
        cg=self.updateCoupling()
        if closures:cg.propagateClosures()
        
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
   
class PhysicalProperty(Term):
    units=models.ForeignKey(Term,related_name='property_units')

class ParamGroup(models.Model):
    ''' This holds either constraintGroups or parameters to link to components '''
    name=models.CharField(max_length=64,default="Attributes")
    def copy(self):
        new=ParamGroup(name=self.name)
        new.save()
        for constraint in self.constraintgroup_set.all():constraint.copy(new)
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
        for param in self.baseparam_set.all(): param.copy(new)
        
class BaseParam(ParentModel):
    ''' Base class for parameters within constraint groups '''
    # We can't the name of this is a value in vocab, because it might be user generated '''
    name=models.CharField(max_length=64,blank=False)
    # lives in 
    constraint=models.ForeignKey(ConstraintGroup)
    #strictly we don't need the following attribute, but it simplifies template code
    controlled=models.BooleanField(default=False)
    # should have definition
    definition=models.CharField(max_length=512,null=True,blank=True)
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
            for m in obj.value.all(): o.value.add(m)
        return o
        
class OrParam(BaseParam):
    value=models.ManyToManyField(Term)
    vocab=models.ForeignKey(Vocab,blank=True,null=True)
    def __unicode__(self):
        s='%s:'%self.name+','.join([a for a in self.value.all()])
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
    value=models.CharField(max_length=128,blank=True,null=True)
    # but it might be a numeric parameter, in which case we have more attributes
    units=models.CharField(max_length=128,null=True,blank=True)
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
        else: return self.title[0:31]  # truncation ...
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
        for af in self.associatedFiles.all():new.associatedFiles.add(af)
        # now copy all the individual couplings associated with this group
        cset=self.coupling_set.all()
        for c in cset: c.copy(new)
        return new
    def propagateClosures(self):
        ''' This is a one stop shop to update all the closures from an original source
        model coupling group to a simulation coupling group '''
        if self.original is None:raise ValueError('No original coupling group available')
        #start by finding all the couplings in this coupling set.
        myset=self.coupling_set.all()
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
    def __unicode__(self):
        if self.parent.simulation:
            return 'CouplingFor:%s(in %s)'%(self.targetInput,self.parent.simulation)
        else:
            return 'CouplingFor:%s'%self.targetInput
    def copy(self,group):
        '''Make a copy of self, and associate with a new group'''
        # first make a copy of self
        args=['inputTechnique','couplingFreq','FreqUnits','manipulation','targetInput']
        kw={'original':self,'parent':group}
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
            set=cmodel.objects.filter(coupling=self.original)
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
        
class Ensemble(models.Model):
    description=models.TextField(blank=True,null=True)
    etype=models.ForeignKey(Term,blank=True,null=True)
    simulation=models.ForeignKey(Simulation)
    def updateMembers(self):
        ''' Make sure we have enough members, this needs to be called if the
        simulation changes it's mind over the number of members '''
        objects=self.ensemblemember_set.all()
        n=len(objects)
        nShouldBe=self.simulation.ensembleMembers
        ndif=n-nShouldBe
        for i in range(abs(ndif)): 
            if ndif >0:
                objects[n-1-i].delete()
            elif ndif < 0:
                e=EnsembleMember(ensemble=self,memberNumber=n+i+1)
                e.save()
    
class EnsembleMember(models.Model):
    ensemble=models.ForeignKey(Ensemble,blank=True,null=True)
    memberNumber=models.IntegerField()
    mod=models.ForeignKey('Modification',blank=True,null=True)
    def __unicode__(self):
        return '%s ensemble member %s'%(self.ensemble.simulation,self.memberNumber)
    class Meta:
        ordering=('memberNumber',)
    
class Conformance(models.Model):
    ''' This relates a numerical requirement to an actual solution in the simulation '''
    # the identifier of the numerical requirement:
    requirement=models.ForeignKey(NumericalRequirement)
    # simulation owning the requirement 
    simulation=models.ForeignKey(Simulation)
    # conformance type from the controlled vocabulary
    ctype=models.ForeignKey(Term,blank=True,null=True)
    #
    mod=models.ManyToManyField('Modification',blank=True,null=True)
    coupling=models.ManyToManyField(Coupling,blank=True,null=True)
    # notes
    description=models.TextField(blank=True,null=True)
    def __unicode__(self):
        return "%s for %s"%(self.ctype,self.requirement)
    
class Modification(ParentModel):
    mnemonic=models.SlugField()
    mtype=models.ForeignKey(Term)
    description=models.TextField()
    centre=models.ForeignKey(Centre)
    def __unicode__(self):
        return '%s(%s)'%(self.mnemonic,self.mtype)
    def get_parent_model(self):
        return Modification
    class Meta:
        ordering=('mnemonic',)
    
    
class InputClosureMod(models.Model):
    ''' Maps onto a specific closure and identifies the modifications to it '''
    coupling=models.ForeignKey(Coupling)
    targetClosure=models.ForeignKey(ExternalClosure)
    targetFile=models.ForeignKey(DataContainer,blank=True,null=True)
    target=models.ForeignKey(DataObject,blank=True,null=True)
    def __unicode__(self):
        return 'Mod to %s %s'%(coupling,targetClosure)
    
class InputMod(Modification):
    ''' Simulation initial condition '''
    # could need a date to override the date in the file for i.c. ensembles.
    # So we use this when the date we want in the model overrides the one in the file.
    revisedDate=models.DateField(blank=True,null=True) # watch out, model calendars
    # could be to multiple inputs ... otherwise it'd get untidy
    revisedInputs=models.ManyToManyField(Coupling,blank=True,null=True)
    # always set these based on the revisedInputs
    revisedClosures=models.ManyToManyField(InputClosureMod,blank=True,null=True)
         
class ModelMod(Modification):
    #we could try and get to the parameter values as well ...
    component=models.ForeignKey(Component)
    
class Grid(Doc):
    properties=models.ManyToManyField(ParamGroup)
    
class DRSOutput(models.Model):
    ''' This is a holding class for how a simulation relates to it's output in the DRS '''
    activity=models.CharField(max_length=64)
    product=models.CharField(max_length=64)
    institute=models.ForeignKey(Centre)
    model=models.ForeignKey(Component)
    experiment=models.ForeignKey(Experiment)
    frequency=models.ForeignKey(Term,blank=True,null=True,related_name='drs_frequency')
    realm=models.ForeignKey(Term,related_name='drs_realm')
    grid=models.ForeignKey(Grid)
    # we don't need to point to simulations, they point to this ...

class DocFeed(Feed):
    ''' This is the atom feed for xml documents available from the questionnaire '''
    # See http://code.google.com/p/django-atompub/wiki/UserGuide
    feeds={'platform':CIMObject.objects.filter(cimtype='platform'),
           'simulation':CIMObject.objects.filter(cimtype='simulation'),
           'component':CIMObject.objects.filter(cimtype='component'),
           'experiment':CIMObject.objects.filter(cimtype='experiment'),
           'files':CIMObject.objects.filter(cimtype='dataContainer'),
           'all':CIMObject.objects.all()}
    
    def _myurl(self,model):
        return 'http://ceda.ac.uk'+reverse('django.contrib.syndication.views.feed',args=('cmip5/%s'%model,))
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
    def item_summary(self,item):
        if item.description:
            return item.description
        else:
            return '%s:%s'%(item.cimtype,item.title)
    def item_content(self,item):
        ''' Return out of line link to the content'''
        return {"type": "application/xml", "src": item.get_absolute_url()},""

