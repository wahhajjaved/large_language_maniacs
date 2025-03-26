from django.db import models
from django.contrib.postgres.fields import ArrayField
import scoping, parliament
from django.contrib.auth.models import User
import numpy as np
import random
from scipy.sparse import csr_matrix, coo_matrix
from MulticoreTSNE import MulticoreTSNE as mTSNE
import os
from datetime import timedelta
from django.db.models.functions import Ln
from django.db.models import F

class MinMaxFloat(models.FloatField):
    """
    A float field with a minimum and a maximum
    """
    def __init__(self, min_value=None, max_value=None, *args, **kwargs):
        self.min_value, self.max_value = min_value, max_value
        super(MinMaxFloat, self).__init__(*args, **kwargs)

    def formfield(self, **kwargs):
        defaults = {'min_value': self.min_value, 'max_value' : self.max_value}
        defaults.update(kwargs)
        return super(MinMaxFloat, self).formfield(**defaults)

#################################################
## Below are some special model variants for hlda
## method

class HTopic(models.Model):
    """
    A model for hierarchical topics
    """
    topic = models.AutoField(primary_key=True)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True)
    title = models.CharField(max_length=80, null=True)
    n_docs = models.IntegerField(null=True)
    n_words = models.IntegerField(null=True)
    scale = models.FloatField(null=True)
    run_id = models.IntegerField(null=True, db_index=True)

class HTopicTerm(models.Model):
    """
    Links hierarchical topics to terms
    """
    topic = models.ForeignKey('HTopic', on_delete=models.CASCADE)
    term = models.ForeignKey('Term', on_delete=models.CASCADE)
    count = models.IntegerField()
    run_id = models.IntegerField(null=True, db_index=True)


#################################################
## Topic, Term and Doc are the three primary models
class Topic(models.Model):
    """
    The default topic object. The title is usually set according to the top words
    """
    title = models.CharField(max_length=80)
    manual_title = models.CharField(max_length=80, null=True)
    original_title = models.CharField(max_length=80, null=True)
    score = models.FloatField(null=True)
    share = models.FloatField(null=True)
    growth = models.FloatField(null=True)
    run_id = models.ForeignKey('RunStats',db_index=True, on_delete=models.CASCADE)
    year = models.IntegerField(null=True)
    period = models.ForeignKey('TimePeriod', on_delete=models.SET_NULL, null=True)
    primary_dtopic = models.ManyToManyField('DynamicTopic')
    top_words = ArrayField(models.TextField(),null=True)
    primary_wg = models.IntegerField(null=True)
    wg_prop = models.FloatField(null=True)
    ipcc_coverage = models.FloatField(null=True)
    ipcc_score = models.FloatField(null=True)
    ipcc_share = models.FloatField(null=True)

    wg_1 = models.FloatField(null=True)
    wg_2 = models.FloatField(null=True)
    wg_3 = models.FloatField(null=True)

    def relevant_words(self, l, n):
        # https://www.aclweb.org/anthology/W14-3110
        tts = self.topicterm_set.annotate(
            share = F('score') / F('alltopic_score'),
            rel = l * Ln('score') + (1-l) * Ln('share'),
        ).filter(rel__isnull=False).order_by('-rel')[:n].values('term__title','rel')
        return tts

    def create_wordintrusion(self,user):
        real_words = self.topicterm_set.order_by('-score')[:5]

        scores = np.array(TopicTerm.objects.filter(topic__run_id=self.run_id).values_list('score', flat=True))
        q99 = np.quantile(scores, 0.99)
        q50 = np.quantile(scores, 0.5)
        terms = set(Term.objects.filter(
            topicterm__score__gt=q99,topicterm__topic__run_id=self.run_id
        ).values_list('pk',flat=True))
        bad_terms = Term.objects.filter(
            pk__in=terms,
            topicterm__score__lt=q50,
            topicterm__topic=self
        )
        if bad_terms.exists():
            bad_term = bad_terms[random.randint(0,bad_terms.count()-1)]
        else:
            bad_term = Term.objects.filter(topicterm__topic=self).order_by('topicterm__score')[0]
        word_intrusion = WordIntrusion(
            topic=self,
            user=user,
            intruded_word=bad_term
        )
        word_intrusion.save()
        for w in real_words:
            word_intrusion.real_words.add(w.term)

    def __unicode__(self):
        return str(self.title)

    def __str__(self):
        return str(self.title)

class WordIntrusion(models.Model):
    """
    Used to assess topic quality, in a given topic, can a user identify the
    intruding word
    """
    topic = models.ForeignKey('Topic', on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    real_words = models.ManyToManyField('Term')
    intruded_word = models.ForeignKey('Term', on_delete=models.CASCADE, related_name="intruding_topic")
    score = models.IntegerField(null=True)

class TopicIntrusion(models.Model):
    """
    Used to assess topic quality, in a given document, can a user identify the
    intruding topic
    """
    doc = models.ForeignKey('scoping.Doc', on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    real_topics = models.ManyToManyField('Topic')
    intruded_topic = models.ForeignKey('Topic', on_delete=models.CASCADE, related_name="intruding_doc")
    score = models.IntegerField(null=True)


class DynamicTopic(models.Model):
    """
    Holds the title, score and other information about dynamic topic models (dynamic nmf).
    todo: is this used only for dynamic nmf?
    """
    title = models.CharField(null=True, max_length=80)
    score = models.FloatField(null=True)
    share = models.FloatField(null=True)
    size = models.IntegerField(null=True)
    run_id = models.ForeignKey('RunStats', on_delete=models.CASCADE,db_index=True)
    top_words = ArrayField(models.TextField(),null=True)
    l5ys = models.FloatField(null=True)
    l1ys = models.FloatField(null=True)
    primary_wg = models.IntegerField(null=True)
    ipcc_time_score = models.FloatField(null=True)
    ipcc_coverage = models.FloatField(null=True)
    ipcc_score = models.FloatField(null=True)
    ipcc_share = models.FloatField(null=True)
    wg_prop = models.FloatField(null=True)

    wg_1 = models.FloatField(null=True)
    wg_2 = models.FloatField(null=True)
    wg_3 = models.FloatField(null=True)

    def __unicode__(self):
        return str(self.title)

    def __str__(self):
        return str(self.title)


class TimePeriod(models.Model):
    """
    Model for a general time period (can be related to a parliamentary period with start and end date)
    """
    title = models.CharField(null=True, max_length=80)
    parlperiod = models.ForeignKey('parliament.ParlPeriod', null=True, on_delete=models.SET_NULL)
    n = models.IntegerField()
    ys = ArrayField(models.IntegerField(),null=True)
    start_date = models.DateField(null=True)
    end_date = models.DateField(null=True)

    def __str__(self):
        return str(self.title)


class TimeDocTotal(models.Model):
    """
    Aggregates scores from a :model:`tmv_app.TimePeriod`
    """
    period = models.ForeignKey(TimePeriod, on_delete=models.PROTECT)
    run = models.ForeignKey('RunStats', on_delete=models.CASCADE)
    n_docs = models.IntegerField(null=True)
    dt_score = models.FloatField(null=True)


class TimeDTopic(models.Model):
    """
    Holds the score of a :model:`tmv_app.DynamicTopic` within a :model:`tmv_app.TimePeriod`
    """
    period = models.ForeignKey(TimePeriod, on_delete=models.PROTECT)
    dtopic = models.ForeignKey('DynamicTopic', on_delete=models.CASCADE)
    score = models.FloatField(default=0)
    share = models.FloatField(default=0)
    pgrowth = models.FloatField(null=True)
    pgrowthn = models.FloatField(null=True)
    ipcc_score = models.FloatField(null=True)
    ipcc_coverage=models.FloatField(null=True)
    ipcc_share = models.FloatField(null=True)


class TopicDTopic(models.Model):
    """
    Holds the score of a :model:`tmv_app.Topic` within a :model:`tmv_app.DynamicTopic`
    """
    topic = models.ForeignKey('Topic', on_delete=models.CASCADE, null=True)
    dynamictopic = models.ForeignKey('DynamicTopic', on_delete=models.CASCADE,null=True)
    score = models.FloatField(null=True)

class TopicCorr(models.Model):
    """
    Holds the correlation between two :model:`tmv_app.Topic` s
    todo: specify which type of correlation?
    """
    topic = models.ForeignKey('Topic', on_delete=models.CASCADE,null=True)
    topiccorr = models.ForeignKey('Topic', on_delete=models.CASCADE ,null=True, related_name='Topiccorr')
    score = models.FloatField(null=True)
    ar = models.IntegerField(default=-1)
    period = models.ForeignKey('TimePeriod', on_delete=models.SET_NULL, null=True)
    run_id = models.IntegerField(db_index=True)

    def __unicode__(self):
        return str(self.title)

class DynamicTopicCorr(models.Model):
    """
    Holds the correlation between two :model:`tmv_app.DynamicTopic` s
    """
    topic = models.ForeignKey('DynamicTopic', on_delete=models.CASCADE,null=True)
    topiccorr = models.ForeignKey('DynamicTopic', on_delete=models.CASCADE,null=True, related_name='Topiccorr')
    score = models.FloatField(null=True)
    ar = models.IntegerField(default=-1)
    period = models.ForeignKey('TimePeriod', on_delete=models.SET_NULL, null=True)
    run_id = models.IntegerField(db_index=True)

    def __unicode__(self):
        return str(self.title)


class Term(models.Model):
    """
    Terms (tokens) of topic models
    """
    title = models.CharField(max_length=100, db_index=True)
    run_id = models.ManyToManyField('RunStats')

    def __unicode__(self):
        return str(self.title)
    def __str__(self):
        return str(self.title)

#################################################
## Docs are all in scoping now!
## todo: think about how to link specific document types to a generalized document model

#################################################

class TopicYear(models.Model):
    """
    Holds total scores of topics per year
    """
    topic = models.ForeignKey('Topic', on_delete=models.CASCADE,null=True)
    PY = models.IntegerField()
    score = models.FloatField(null=True)
    share = models.FloatField(null=True)
    count = models.FloatField(null=True)
    run_id = models.IntegerField(db_index=True)


class TopicARScores(models.Model):
    """
    Holds total scores of topics per Assessment period (:model:`scoping:AR`)

    todo: could this be replaced by linking the general TimePeriod to AR?
    """
    topic = models.ForeignKey('Topic', on_delete=models.CASCADE,null=True)
    ar = models.ForeignKey('scoping.AR', on_delete=models.CASCADE,null=True)
    score = models.FloatField(null=True)
    share = models.FloatField(null=True)
    pgrowth = models.FloatField(null=True)
    pgrowthn = models.FloatField(null=True)


class TopicTimePeriodScores(models.Model):
    """
    Holds scores of a :model:`tmv_app.Topic` from a :model:`tmv_app.TimePeriod`
    """
    topic = models.ForeignKey('Topic', on_delete=models.CASCADE, null=True)
    period = models.ForeignKey('TimePeriod', on_delete=models.SET_NULL, null=True)
    score = models.FloatField(null=True)
    share = models.FloatField(null=True)
    pgrowth = models.FloatField(null=True)
    pgrowthn = models.FloatField(null=True)


class DynamicTopicARScores(models.Model):
    """
    Holds scores of a :model:`tmv_app.DynamicTopic` from an Assessment Period (:model:`scoping.AR`)
    """
    topic = models.ForeignKey('DynamicTopic', on_delete=models.CASCADE, null=True)
    ar = models.ForeignKey('scoping.AR', on_delete=models.SET_NULL, null=True)
    score = models.FloatField(null=True)
    share = models.FloatField(null=True)
    pgrowth = models.FloatField(null=True)
    pgrowthn = models.FloatField(null=True)


class DynamicTopicTimePeriodScores(models.Model):
    """
    Holds scores of a :model:`tmv_app.DynamicTopic` from a :model:`TimePeriod`
    """
    topic = models.ForeignKey('DynamicTopic', on_delete=models.CASCADE,null=True)
    period = models.ForeignKey('TimePeriod', on_delete=models.SET_NULL, null=True)
    score = models.FloatField(null=True)
    share = models.FloatField(null=True)
    pgrowth = models.FloatField(null=True)
    pgrowthn = models.FloatField(null=True)


#################################################
## Separate topicyear for htopic
class HTopicYear(models.Model):
    """
    todo
    """
    topic = models.ForeignKey('HTopic', on_delete=models.CASCADE, null=True)
    PY = models.IntegerField()
    score = models.FloatField()
    count = models.FloatField()
    run_id = models.IntegerField(db_index=True)

#################################################
## DocTopic and TopicTerm map contain topic scores
## for docs and topics respectively


class DocTopic(models.Model):
    """
    Relates :model:`scoping.Doc` or objects from parliament (paragraphs, speeches) with :model:`tmv_app.Topics` and holds the corresponding topic scores
    """
    doc = models.ForeignKey('scoping.Doc', null=True, on_delete=models.SET_NULL)
    par = models.ForeignKey('parliament.Paragraph',null=True, on_delete=models.SET_NULL)
    ut = models.ForeignKey('parliament.Utterance',null=True, on_delete=models.SET_NULL)
    topic = models.ForeignKey('Topic',null=True, on_delete=models.CASCADE)
    score = models.FloatField()
    scaled_score = models.FloatField()
    run_id = models.IntegerField(db_index=True)

class DocDynamicTopic(models.Model):
    """
    Relates :model:`scoping.Doc` with :model:`tmv_app.Topic` and holds the corresponding topic score
    """
    doc = models.ForeignKey('scoping.Doc', null=True, on_delete=models.SET_NULL)
    topic = models.ForeignKey('DynamicTopic',null=True, on_delete=models.CASCADE)
    score = models.FloatField()
    run_id = models.IntegerField(db_index=True)


class TopicTerm(models.Model):
    """
    Relates :model:`tmv_app.Topic` with :model:`tmv_app.Term` and holds the corresponding term score
    """
    topic = models.ForeignKey('Topic',null=True, on_delete=models.CASCADE)
    term = models.ForeignKey('Term', on_delete=models.SET_NULL, null=True)
    PY = models.IntegerField(db_index=True,null=True)
    score = models.FloatField()
    alltopic_score = models.FloatField(null=True)
    run_id = models.IntegerField(db_index=True)

class DynamicTopicTerm(models.Model):
    """
    Relates :model:`tmv_app.DynamicTopic` with :model:`tmv_app.Term` and holds the corresponding term score
    """
    topic = models.ForeignKey('DynamicTopic', null=True, on_delete=models.CASCADE)
    term = models.ForeignKey('Term', on_delete=models.SET_NULL, null=True)
    PY = models.IntegerField(db_index=True, null=True)
    score = models.FloatField()
    run_id = models.IntegerField(db_index=True)

class KFold(models.Model):
    """
    Stores information from K-fold model validation (see tasks.py: function k_fold)
    """
    model = models.ForeignKey('RunStats', on_delete=models.CASCADE)
    K = models.IntegerField()
    error = models.FloatField(null=True)


class TermPolarity(models.Model):
    """
    Records the polarity of :model:`tmv_app:Term` (for sentiment analysis using a dictionary approach)
    """
    term = models.ForeignKey(Term, on_delete=models.CASCADE)
    polarity = models.FloatField(null=True)
    POS = models.TextField(null=True, verbose_name="part of speech")
    source = models.TextField()


#################################################
## RunStats and Settings....
class RunStats(models.Model):
    """
    Hold all meta-information on topic model runs
    """
    run_id = models.AutoField(primary_key=True)

    ##Inputs

    ONLINE = "on"
    BATCH = "ba"
    lda_choices = (
        (ONLINE, 'Online'),
        (BATCH, 'Batch'),
    )
    SKLEARN = "sk"
    LDA_LIB = "ld"
    lda_libs = (
        (SKLEARN, "Sklearn"),
        (LDA_LIB, "lda")
    )

    max_features = models.IntegerField(default=0, help_text = 'Maximum number of terms (0 = no limit)')
    min_freq = models.IntegerField(default=1, help_text = 'Minimum frequency of terms')
    max_df = MinMaxFloat(default=0.95, min_value=0.0, max_value=1.0)
    limit = models.IntegerField(null=True, default=0, help_text='Limit model to first x documents (leave as zero for no limit)')
    ngram = models.IntegerField(null=True, default=1, help_text='Length of feature n_gram')
    db = models.BooleanField(default=True, help_text='Record the results into the database? Or just run the model and record statistics?')

    fancy_tokenization = models.BooleanField(default=False, help_text='tokenize so that multiple word keywords remain whole')

    K = models.IntegerField(null=True, help_text='Number of topics')
    alpha = models.FloatField(null=True, default=0.01, help_text='Concentration parameter of Dirichlet distribution of topics in documents'
                                                                 '(try higher values in LDA, including > 1). Low (high) values indicate that'
                                                                 'documents should be composed of few (many) topics. Also called theta.')
    beta = models.FloatField(null=True, default=None, help_text='Concentration parameter of Dirichlet distribution of words in topics.'
                                                                'Low (high) values indicate that topics should be composed of few (many) words.'
                                                                'Also called eta.')
    lda_learning_method = models.CharField(max_length = 2, choices=lda_choices, null=True, default=BATCH, help_text='When using LDA in sklearn, you can choose between batch or online learning')
    lda_library = models.CharField(max_length = 2, choices=lda_libs, null=True, default=SKLEARN,help_text = 'you can use sklearn or https://github.com/lda-project/lda for LDA')
    top_chain_var = models.FloatField(null=True, default=0.05, help_text='Chain var parameter for dtm')
    max_iter = models.IntegerField(null=True, default=200, help_text='Maximum iterations')
    rng_seed = models.IntegerField(null=True, help_text="seed for random number generator for stochastic estimation of topic model (blei dtm)")
    fulltext = models.BooleanField(default=False, help_text='do analysis on fullText? (dependent on availability)')
    citations = models.BooleanField(default=False, help_text='scale term scores by citations?')

    # Additional information
    language = models.TextField(null=True, help_text='language of the documents that have been analyzed (also used for stopword identification)')
    extra_stopwords = ArrayField(models.TextField(), null=True, help_text='list of stopwords that are used additionally to the standard ones')

    query = models.ForeignKey('scoping.Query', null=True, on_delete=models.CASCADE, help_text='relation to the scoping search object')
    psearch = models.ForeignKey('parliament.Search',null=True, on_delete=models.CASCADE, help_text='relation to the parliamentary search object')

    ## Progress
    process_id = models.IntegerField(null=True)
    start = models.DateTimeField(auto_now_add=True)
    batch_count = models.IntegerField(default=0)
    last_update = models.DateTimeField(auto_now_add=True)
    topic_titles_current = models.NullBooleanField(default=False)
    topic_scores_current = models.NullBooleanField(default=False)
    topic_year_scores_current = models.NullBooleanField(default=False)

    ## Time spent
    runtime = models.DurationField(null=True)
    nmf_time = models.FloatField(default=0)
    tfidf_time = models.FloatField(default=0)
    db_time = models.FloatField(default=0)

    status_choices = (
        (0,'Not Started'),
        (1,'Running'),
        (2,'Interrupted'),
        (3,'Finished')
    )
    status = models.IntegerField(
        choices = status_choices,
        default = 0,
        help_text='status of the model execution'
    )

    parent_run_id = models.IntegerField(null=True, help_text='')

    docs_seen = models.IntegerField(null=True)
    notes = models.TextField(null=True)
    LDA = 'LD'
    HLDA = 'HL'
    DTM = 'DT'
    NMF = 'NM'
    BDT = 'BD'
    METHOD_CHOICES = (
        (LDA, 'lda'),
        (HLDA, 'hlda'),
        (DTM, 'dnmf'),
        (NMF,'nmf'),
        (BDT,'BleiDTM')
    )
    method = models.CharField(
        max_length=2,
        choices=METHOD_CHOICES,
        default=NMF,
    )
    error = models.FloatField(null=True, default = 0)
    coherence = models.FloatField(null=True)
    errortype = models.TextField(null=True)
    exclusivity = models.FloatField(null=True)

    empty_topics = models.IntegerField(null=True)

    iterations = models.IntegerField(null=True)

    max_topics = models.IntegerField(null=True)
    term_count = models.IntegerField(null=True)
    periods = models.ManyToManyField('TimePeriod')

    doc_topic_scaled_score = models.BooleanField(default=False)
    dt_threshold = models.FloatField(default = 0.0005 )
    dt_threshold_scaled = models.FloatField( default = 0.01)
    dyn_win_threshold = models.FloatField(default = 0.1 )

    def save(self, *args, **kwargs):
        if not self.parent_run_id:
            self.parent_run_id=self.run_id
        super(RunStats, self).save(*args, **kwargs)

    def dt_matrix(self, path, s_size=0, force_overwrite=False):
        '''
        Return a sparse doctopic matrix and its row and column ids
        '''
        # see if the required objects already exist
        mpath = f"{path}/run_{self.pk}_s_{s_size}_m.npy"
        rpath = f"{path}/run_{self.pk}_s_{s_size}_r_ind.npy"
        cpath = f"{path}/run_{self.pk}_s_{s_size}_c_ind.npy"
        if os.path.exists(mpath):
            m = np.load(mpath)
            if os.path.exists(rpath):
                r_ind = np.load(rpath)
                if os.path.exists(cpath):
                    c_ind = np.load(cpath)
                    if not force_overwrite:
                        print("We've already calculated the required matrices!")
                        return(m,c_ind,r_ind)

        if self.method=="DT":
            dts = DocDynamicTopic.objects
        else:
            dts = DocTopic.objects

        if self.query:
            doc_id_var = 'doc__id'
        elif self.psearch:
            if self.psearch.search_object_type==parliament.models.Search.PARAGRAPH:
                doc_id_var = 'ut__id'
            elif self.psearch.search_object_type==parliament.models.Search.UTTERANCE:
                doc_id_var = 'par__id'
        else:
            print("I don't know what type of document I have...")
            return

        db_matrix = dts.filter(
            run_id=self.pk,
            score__gt=self.dt_threshold
        )
        docs = set(db_matrix.values_list(doc_id_var,flat=True))

        if s_size >0:
            s_docs = random.sample(docs,s_size)
            db_matrix = dts.filter(
                run_id=stat.pk,
                score__gt=0.01,
                doc__id__in=s_docs
            )
        vs = list(db_matrix.values('score',doc_id_var,'topic_id'))

        c_ind = np.array(list(set(db_matrix.values_list('topic_id',flat=True).order_by(doc_id_var))))
        r_ind = np.array(list(set(db_matrix.values_list(doc_id_var,flat=True).order_by(doc_id_var))))

        d = [x['score'] for x in vs]
        c = [int(np.where(c_ind==x['topic_id'])[0]) for x in vs]
        r = [int(np.where(r_ind==x['doc__id'])[0]) for x in vs]

        m = coo_matrix((d,(r,c)),shape=(len(r_ind),len(c_ind)))

        np.save(mpath, m)
        np.save(rpath, r_ind)
        np.save(cpath, c_ind)

        return(m,c_ind,r_ind)

    def calculate_tsne(self, path, p, s_size=0, force_overwrite=False):
        """
        Function applied to RunStats object to calculate dimensionality reduction using TSNE

        :param path: Results path
        :param p:
        :param s_size:
        :param force_overwrite: (default: False) Overrides already existing results
        :return:
        """
        m, c_ind, r_ind = self.dt_matrix(path, s_size)
        results_path =  f"{path}/run_{self.pk}_s_{s_size}_p_{p}_results.npy"
        if os.path.exists(results_path):
            tsne_results = np.load(results_path)
            if not force_overwrite:
                print("We've already calculated the tsne positions")
                return tsne_results, r_ind
        tsne = mTSNE(n_components=2, verbose=0, perplexity=p,n_jobs=4)
        tsne_results = tsne.fit_transform(m.toarray())
        np.save(results_path, tsne_results)
        return tsne_results, r_ind


class Settings(models.Model):
    """
    todo: what is this?
    used in utils/db.py and BasisBrowser/db.py
    """
    run_id = models.IntegerField()
    doc_topic_score_threshold = models.FloatField()
    doc_topic_scaled_score = models.BooleanField()
