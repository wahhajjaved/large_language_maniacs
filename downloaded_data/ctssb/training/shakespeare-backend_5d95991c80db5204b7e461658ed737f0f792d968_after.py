import uuid, re
from django.db import models
from django.contrib.postgres.fields import JSONField, ArrayField # JSON + Array Fields
from model_utils.models import TimeStampedModel
from .categories import NUGGET_TEMPLATE_CATEGORIES


class Company(TimeStampedModel):
    domain = models.CharField(unique=True, max_length=100) # Ensure the domain is unique
    clearbit = models.UUIDField() # The clearbit UUID
    name = models.CharField(max_length=100, blank=True, null=True)
    industry = models.CharField(max_length=100, blank=True, null=True)
    sector = models.CharField(max_length=100, blank=True, null=True)
    crunchbase = models.CharField(max_length=100, blank=True, null=True)
    description = models.CharField(max_length=1000, blank=True, null=True)
    logo = models.CharField(max_length=500, blank=True, null=True)
    location = JSONField() #json representation of location

    def __str__(self):
        return "{} ({})".format(str(self.name), str(self.domain))

    class Meta:
        verbose_name = "company"
        verbose_name_plural = "companies"
        ordering = ('created',)


class Individual(TimeStampedModel):
    """
    The individual to which research can be performed on.
    """
    email = models.EmailField(unique=True) # Ensure that this email is unique
    firstname = models.CharField(max_length=100, blank=True, null=True)
    lastname = models.CharField(max_length=100, blank=True, null=True)
    jobtitle = models.CharField(max_length=200, blank=True, null=True)
    role = models.CharField(max_length=200, blank=True, null=True)
    avatar = models.CharField(max_length=500, blank=True, null=True) #URL to an avatar
    company = models.ForeignKey('research.Company', related_name='individual', null=True, on_delete=models.CASCADE) #null=True is because and Individual doesn't have to have a company
    companyname = models.CharField(max_length=200, blank=True, null=True) #We have a company name too, as it's possible for there to be no `company` result from Clearbit, however the person has a 'company name'
    clearbit = models.UUIDField() # The clearbit UUID

    def __str__(self):
        return "{} {} ({})".format(str(self.firstname),str(self.lastname), str(self.email))

    class Meta:
        verbose_name = "individual"
        verbose_name_plural = "individuals"
        ordering = ('created',)


class Research(TimeStampedModel):
    """
    The specific research 'job'
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False) #We'll use a UUID here to help anonymize the location of the results. 
    owner = models.ForeignKey('auth.User', related_name='research', on_delete=models.CASCADE)
    complete = models.BooleanField(default=False)
    individual = models.ForeignKey('research.Individual', related_name='research', on_delete=models.CASCADE)

    def __str__(self):
        return str(self.individual)

    class Meta:
        verbose_name = "research"
        verbose_name_plural = "research"
        ordering = ('created',)



class Piece(TimeStampedModel):
    """
    One 'result' of a search for information for the prospect.
    """
    aggregator = models.TextField(blank=True, default='')
    publisheddate = models.DateTimeField(blank=True, null=True)
    title = models.TextField(blank=True, default='')
    author = models.CharField(max_length=1000, blank=True, default='')
    body = models.CharField(max_length=1000, blank=True, default='')
    source = JSONField(blank=True, null=True) # The actual place on the web we got this from. We'll make this a JSON field for now. Ideally it's a lookup to a 'Data Source' table in the future
    url = models.TextField(blank=True, default='')
    research = models.ForeignKey('research.Research', related_name='piece', on_delete=models.CASCADE) #Lookup the research instance that spawned this
    
    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        self.full_clean()
        super(TimeStampedModel, self).save(*args, **kwargs)

    class Meta:
        verbose_name = "piece"
        verbose_name_plural = "pieces"
        ordering = ('created',)


class Nugget(TimeStampedModel):
    """
    An NLP extracted 'snippet' of quotable/interesting/relevant material found within the body of a 'Piece'
    """
    category = models.CharField(max_length=100, choices=NUGGET_TEMPLATE_CATEGORIES, default='quote')
    body = models.CharField(max_length=1000, blank=True, default='') #The body of text comprising the nugget
    piece = models.ForeignKey('research.Piece', related_name='nugget', on_delete=models.CASCADE) #Lookup the research instance that spawned this
    additionaldata = JSONField(null=True) # all the varying values to be merged into a wrapper
    
    def __str__(self):
        return self.body

    def get_mergefields(self):
        return self.additionaldata.keys() if (self.additionaldata is not None) else []
        #return self.additionaldata.keys() # The keys of the additionaldata are the mergefields in the NuggetTemplate


    def save(self, *args, **kwargs):
        self.full_clean()
        super(TimeStampedModel, self).save(*args, **kwargs)


    class Meta:
        verbose_name = "nugget"
        verbose_name_plural = "nuggets"
        ordering = ('created',)

class NuggetTemplate(TimeStampedModel):
    """
    The pre-created 'templates' that present a values from a 'Nugget' in an 'email presentable' way. The convention for the replace strings
    Is as follows: {{Model.fieldname}}. If that field happens to be a jsonfield then one more level of nesting should be used. e.g.
    {{Individual.firstname}} or {{Nugget.additionaldata.company}}
    """
    subject = models.CharField(max_length=200, default='')
    intro = models.TextField(blank=True, default='')
    segue = models.TextField(blank=True, default='')
    category = models.CharField(max_length=100, choices=NUGGET_TEMPLATE_CATEGORIES, default='quote')
    mergefields = ArrayField(models.CharField(max_length=100), blank=True)

    def save(self, *args, **kwargs):
        merges = re.findall("{{Nugget.additionaldata.(.*?)}}", self.intro + self.subject + self.segue) #get all the nugget additionaldata template names from within the mustaches
        self.mergefields = list(set(merges)) #unique them
        super(TimeStampedModel, self).save(*args, **kwargs)


    # TODO: Investigate DRY way to merge in any arbitrary model using Model = apps.get_model(app_label='research', model_name=model)
    # template is the string template to have values merged into it.
    def merge(self, template, nugget):
        models = list(set(re.findall("{{(.*?)\.", template))) #get all the unique models that will be merged
        if 'Individual' in models:
            fields = list(set(re.findall("{{Individual.(.*?)}}", template)))
            for field in fields:
                template = re.sub(r"{{Individual."+field+"}}", getattr(nugget.piece.research.individual, field), template)
        if ('Company' in models) and (nugget.piece.research.individual.company is not None):
            fields = list(set(re.findall("{{Company.(.*?)}}", template)))
            for field in fields:
                template = re.sub(r"{{Company."+field+"}}", getattr(nugget.piece.research.individual.company, field), template)
        if 'Nugget' in models:
            fields = list(set(re.findall("{{Nugget\.(.*?)(?:}}|\.)", template))) 
            for field in fields:
                if field == 'additionaldata':
                    additionaldatafields = list(set(re.findall("{{Nugget.additionaldata\.(.*?)}}", template)))
                    for additionaldatafield in additionaldatafields:
                        template = re.sub(r"{{Nugget.additionaldata."+additionaldatafield+"}}", str(nugget.additionaldata[additionaldatafield]), template)
                else:
                    template = re.sub(r"{{Nugget."+field+"}}", getattr(nugget, field), template)
        return template

    def __str__(self):
        return "{} ({})".format(str(self.subject), str(self.category))

    class Meta:
        verbose_name = "nugget template"
        verbose_name_plural = "nugget templates"
        ordering = ('created',)

