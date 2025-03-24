from __future__ import absolute_import, unicode_literals
from celery import shared_task
from parliament.models import *
from cities.models import Region
from tmv_app.models import *
from utils.utils import flatten
import os, sys, gc
from utils.text import german_stemmer, snowball_stemmer, process_texts
from utils.tm_mgmt import update_topic_titles, update_topic_scores
from sklearn.feature_extraction.text import TfidfVectorizer, CountVectorizer
from scipy.sparse import csr_matrix, find
from sklearn.decomposition import NMF, LatentDirichletAllocation as LDA
import random
import utils.db as db
from multiprocess import Pool
from functools import partial
from nltk.stem import SnowballStemmer
from nltk.corpus import stopwords
import time
import django.db
from django.utils import timezone
from parliament.utils import merge_utterance_paragraphs

from parliament.run_dynamic_nmf import run_dynamic_nmf
from parliament.run_blei_dtm import run_blei_dtm


# ===================================================================================================================
# ===================================================================================================================


@shared_task
def do_search(s_id):
    s = Search.objects.get(pk=s_id)
    if s.search_object_type == 1: # paragraphs
        s.paragraph_set.clear()  # delete old search matches
        ps = Paragraph.objects.filter(text__iregex=s.text)

        if s.document_source:
            ps = ps.filter(utterance__document__text_source__iregex=s.document_source)
        if s.start_date:
            ps = ps.filter(utterance__document__date__gte=s.start_date)
        if s.stop_date:
            ps = ps.filter(utterance__document__date__lte=s.stop_date)

        print("{} paragraphs with search {}".format(ps.count(), s.text))

        # filter for parties
        if s.party is not None:
            ps = ps.filter(utterance__speaker__party=s.party)
            print("{} paragraphs left after filtering for party: {}".format(ps.count(), s.party))

        # filter for regions
        if s.speaker_regions.exists():
            # differentiate between different seat types (list or direct mandate):
            # list: speaker -> seat -> partylist -> region
            ps_list = ps.filter(utterance__speaker__seat__seat_type=2).distinct()
            ps_list = ps_list.filter(utterance__speaker__seat__list__region__in=s.speaker_regions.all())
            print("paragraphs attributed to list mandates in regions: {}".format(ps_list.count()))

            # direct: speaker -> seat -> consituency -> region
            ps_direct = ps.filter(utterance__speaker__seat__seat_type=1).distinct()
            ps_direct = ps_direct.filter(utterance__speaker__seat__constituency__region__in=s.speaker_regions.all())
            ps = ps_list.union(ps_direct)
            print("paragraphs attributed to direct mandates in regions: {}".format(ps_direct.count()))

            print("{} paragraphs left after filtering for regions: {}".format(ps.count(), [r.name for r in s.speaker_regions.all()]))

        # this only saves the right numbers if run for the second time
        par_count = ps.count()
        s.par_count = par_count
        utterance_count = Utterance.objects.filter(paragraph__in=ps).distinct().count()
        s.utterance_count = utterance_count
        print(par_count)
        print(utterance_count)
        s.save(force_update=True)
        Through = Paragraph.search_matches.through
        tms = [Through(paragraph=p,search=s) for p in ps]
        Through.objects.bulk_create(tms)
        s.save()
        return tms

    elif s.search_object_type == 2: # utterances
        s.utterance_set.clear()  # delete old search matches

        ut = Utterance.objects.filter(paragraph__text__iregex=s.text).distinct()

        if s.document_source:
            ut = ut.filter(document__text_source__iregex=s.document_source)
        if s.start_date:
            ut = ut.filter(document__date__gte=s.start_date)
        if s.stop_date:
            ut = ut.filter(document__date__lte=s.stop_date)

        print("{} utterances with search {}".format(ut.count(), s.text))

        # filter for parties
        if s.party is not None:
            ut = ut.filter(speaker__party=s.party)
            print("{} paragraphs left after filtering for party: {}".format(ut.count(), s.party))

        # filter for regions
        if s.speaker_regions.exists():
            # differentiate between different seat types (list or direct mandate):
            # list: speaker -> seat -> partylist -> region
            ut_list = ut.filter(speaker__seat__seat_type=2).distinct()
            ut_list = ut_list.filter(speaker__seat__list__region__in=s.speaker_regions.all())
            print("utterances attributed to list mandates in regions: {}".format(ut_list.count()))

            # direct: speaker -> seat -> consituency -> region
            ut_direct = ut.filter(speaker__seat__seat_type=1).distinct()
            ut_direct = ut_direct.filter(speaker__seat__constituency__region__in=s.speaker_regions.all())
            ut = ut_list.union(ut_direct)
            print("utterances attributed to direct mandates in regions: {}".format(ut_direct.count()))

            print("{} utterances left after filtering for regions: {}".format(ut.count(),
                                                                              [r.name for r in s.speaker_regions.all()]))

        utterance_count = ut.count()
        s.utterance_count = utterance_count
        par_count = Paragraph.objects.filter(utterance__in=ut).count()
        print(par_count)
        print(utterance_count)
        s.par_count = par_count
        s.save(force_update=True)
        Through = Utterance.search_matches.through
        tms = [Through(utterance=u, search=s) for u in ut]
        Through.objects.bulk_create(tms)
        s.save()
        return tms

    else:
        print("search_object_type not valid ({})".format(s.search_object_type))
        return

@shared_task
def combine_searches(s_ids):

    searches = Search.objects.filter(pk__in=s_ids)

    # check whether search object are of the same type
    object_types = set(list(searches.values_list('search_object_type')))
    if len(object_types) > 1:
        print("search object type does not match, did not merge")
        return
    else:
        print("all search object types identical")

    # create new search object

    search_object_type = list(object_types)[0][0]
    s = Search(title='Searches {} combined'.format(", ".join([str(s_id) for s_id in s_ids])))
    s.search_object_type = search_object_type
    s.project = searches[0].project
    s.save()
    if search_object_type == 2:
        ut = Utterance.objects.filter(search_matches__in=searches).distinct()
        Through = Utterance.search_matches.through
        tms = [Through(utterance=u, search=s) for u in ut]
        Through.objects.bulk_create(tms)
        s.utterance_count = ut.count()
    elif search_object_type == 1:
        pars = Paragraph.objects.filter(search_matches__in=searches).distinct()
        Through = Paragraph.search_matches.through
        tms = [Through(paragraph=p, search=s) for p in pars]
        Through.objects.bulk_create(tms)
        s.par_count = pars.count()
    s.save()

    print("Created combined search: id = {}".format(s.id))

    return

# ==================================================================================================================
# ===================================================================================================================

@shared_task
def run_tm(s_id, K, language="german", verbosity=1, method='NM', max_features=0, max_df=0.95, min_df=5, alpha=0.01,
           extra_stopwords=set(), top_chain_var=None, rng_seed=None, max_iter=200, **kwargs):

    if method in ['DT', 'dnmf', 'BD', 'BleiDTM'] and max_features == 0:
        max_features = 20000
    if method in ['BD', 'BleiDTM'] and top_chain_var is None:
        top_chain_var = 0.005

    s = Search.objects.get(pk=s_id)
    stat = RunStats(
        psearch=s,
        K=K,
        min_freq=min_df,
        max_df=max_df,
        method=method.upper()[0:2],
        max_features=max_features,
        max_iter=max_iter,
        alpha=alpha,
        extra_stopwords=list(extra_stopwords),
        top_chain_var=top_chain_var,
        status=1,
        language=language
    )
    stat.save()
    django.db.connections.close_all()

    if method in ['DT', 'dnmf']:
        print("Running dynamic NMF algorithm")
        run_dynamic_nmf(stat, **kwargs)
        return 0
    elif method in ['BD', 'BleiDTM']:
        print("Running Blei DTM algorithm")
        if rng_seed:
            stat.rng_seed = rng_seed
        else:
            stat.rng_seed = 1
        stat.save()
        run_blei_dtm(stat, **kwargs)
        return 0

    print("starting topic model for runstat with settings:")
    for field in stat._meta.fields:
        field_value = getattr(stat, field.name)
        if field_value:
            print("{}: {}".format(field.name, field_value))

    start_time = time.time()
    start_datetime = timezone.now()

    stat.status = 1  # 3 = finished

    stat.save()
    run_id=stat.run_id

    if s.search_object_type == 1:
        ps = Paragraph.objects.filter(search_matches=s)
        docs = ps.filter(text__iregex='\w')
        texts, docsizes, ids = process_texts(docs)

    elif s.search_object_type == 2:
        uts = Utterance.objects.filter(search_matches=s)
        texts, docsizes, ids = merge_utterance_paragraphs(uts)
    else:
        print("search object type invalid")
        return 1

    if stat.max_features == 0:
        n_features=1000000
    else:
        n_features = stat.max_features

    if stat.language is "german":
        stemmer = SnowballStemmer("german")
        tokenizer = german_stemmer()
        stopword_list = [stemmer.stem(t) for t in stopwords.words("german")]

    elif stat.language is "english":
        stemmer = SnowballStemmer("english")
        stopword_list = [stemmer.stem(t) for t in stopwords.words("english")]
        tokenizer = snowball_stemmer()
    else:
        print("Language not recognized.")
        return 1

    if stat.extra_stopwords:
        stopword_list = list(set(stopword_list) | set(stat.extra_stopwords))

    if method in ["NM", "nmf"]:
        if verbosity > 0:
            print("creating term frequency-inverse document frequency matrix ({})".format(time.time() - start_time))
        # get term frequency-inverse document frequency matrix (using log weighting)
        # and min/max document frequency (min_df, max_df)
        tfidf_vectorizer = TfidfVectorizer(
            max_df=stat.max_df,
            min_df=stat.min_freq,
            max_features=n_features,
            ngram_range=(1, stat.ngram),
            tokenizer=tokenizer,
            stop_words=stopword_list
            )

        tfidf = tfidf_vectorizer.fit_transform(texts)
        vectorizer = tfidf_vectorizer
        vocab = vectorizer.get_feature_names()

    elif method in ["LD", "lda"]:
        if verbosity > 0:
            print("creating term frequency matrix ({})".format(time.time() - start_time))
        #  Use tf (raw term count) features for LDA.
        tf_vectorizer = CountVectorizer(max_df=stat.max_df,
                                        min_df=stat.min_freq,
                                        max_features=n_features,
                                        ngram_range=(1, stat.ngram),
                                        tokenizer=tokenizer,
                                        stop_words=stopword_list)
        tf = tf_vectorizer.fit_transform(texts)
        vectorizer = tf_vectorizer
        vocab = vectorizer.get_feature_names()
    else:
        print("method not implemented")
        return 1


    if verbosity > 0:
        print("save terms to db ({})".format(time.time() - start_time))

    paralellized = True
    if paralellized:
        vocab_ids = []
        # multiprocessing: add vocabulary as Term
        pool = Pool(processes=8)
        vocab_ids.append(pool.map(partial(db.add_features,run_id=run_id),vocab))
        pool.terminate()
        del vocab
        vocab_ids = vocab_ids[0]

    else:
        print("without multiprocessing for storing terms")
        # without multiprocessing
        objects = [Term(title=term_title) for term_title in vocab]

        # TODO: if some of the objects already exist, duplicates are created: use uniqueness of field 'title'
        Term.objects.bulk_create(objects)
        runstats = RunStats.objects.get(run_id=run_id)
        runstats.term_set.add(*objects)
        runstats.save()


    ## Make some topics
    django.db.connections.close_all()
    topic_ids = db.add_topics(K, run_id)
    gc.collect()


    if verbosity > 1:
        v = True
    else:
        v = False

    if method in ["NM", "nmf"]:
        if verbosity > 0:
            print("running matrix factorization with NMF ({})".format(time.time() - start_time))
        # NMF = non-negative matrix factorization
        model = NMF(
            n_components=K, random_state=1,
            alpha=stat.alpha, l1_ratio=.1, verbose=v,
            init='nndsvd', max_iter=stat.max_iter
        ).fit(tfidf)
        # initialization with Nonnegative Double Singular Value Decomposition (nndsvd)
        print("Reconstruction error of nmf: {}".format(model.reconstruction_err_))

        stat.error = model.reconstruction_err_
        stat.errortype = "Frobenius"

        # document topic matrix
        dtm = csr_matrix(model.transform(tfidf))

    elif method in ["LD", "lda"]:
        if verbosity > 0:
            print("running Latent Dirichlet Allocation ({})".format(time.time() - start_time))
        model = LDA(
            n_components=K,
            doc_topic_prior=stat.alpha,  # this is the concentration parameter of the Dirichlet distribution of topics in documents
            topic_word_prior=stat.beta,  # this is the concentration parameter of the Dirichlet distribution of words in topics
                                         # if None, this defaults to 1/n
            max_iter=stat.max_iter,
            learning_method='online',  # using 'batch' instead could lead to memory problems
            learning_offset=50.
            #n_jobs=6
        ).partial_fit(tf)

        stat.error = model.perplexity(tf)
        stat.errortype = "Perplexity"

        dtm = csr_matrix(model.transform(tf))

    else:
        print("Method {} not available.".format(method))
        return 1

    # term topic matrix
    ldalambda = find(csr_matrix(model.components_))
    # find returns the indices and values of the nonzero elements of a matrix
    topics = range(len(ldalambda[0]))
    tts = []
    # multiprocessing: add TopicTerms and scores
    pool = Pool(processes=8)
    tts.append(pool.map(partial(db.f_lambda, m=ldalambda,
                    v_ids=vocab_ids,t_ids=topic_ids,run_id=run_id),topics))
    pool.terminate()

    tts = flatten(tts)
    gc.collect()
    sys.stdout.flush()
    django.db.connections.close_all()
    TopicTerm.objects.bulk_create(tts)

    if verbosity > 0:
        print("saving document topic matrix to db ({})".format(time.time() - start_time))

    #document topic matrix
    gamma = find(dtm)
    glength = len(gamma[0])

    chunk_size = 100000

    no_cores = 16
    parallel_add = True

    all_dts = []

    make_t = 0
    add_t = 0

    ### Go through in chunks
    for i in range(glength//chunk_size+1):
        values_list = []
        f = i*chunk_size
        l = (i+1)*chunk_size
        if l > glength:
            l = glength
        docs = range(f,l)
        doc_batches = []
        for p in range(no_cores):
            doc_batches.append([x for x in docs if x % no_cores == p])
        pool = Pool(processes=no_cores)
        values_list.append(pool.map(partial(
            db.f_gamma_batch, gamma=gamma,
            docsizes=docsizes,docUTset=ids,topic_ids=topic_ids,
            run_id=run_id
        ),doc_batches))
        pool.terminate()
        django.db.connections.close_all()
        values_list = [item for sublist in values_list for item in sublist]
        pool = Pool(processes=no_cores)
        if s.search_object_type == 1:
            pool.map(db.insert_many_pars,values_list)
        elif s.search_object_type == 2:
            pool.map(db.insert_many_utterances,values_list)
        pool.terminate()
        gc.collect()
        sys.stdout.flush()

    stat.iterations = model.n_iter_
    stat.status = 3  # 3 = finished
    stat.last_update = timezone.now()
    stat.runtime = timezone.now() - start_datetime
    stat.save()
    update_topic_titles(run_id)
    update_topic_scores(run_id)

    if verbosity > 0:
        print("topic model run done ({})".format(time.time() - start_time))

    return 0


def add_dates_to_parlperiods():
    """
    adds the dates of the first and last documents related to a ParlPeriod to the ParlPeriod object
    """
    pps = ParlPeriod.objects.all()

    for pp in pps:
        print(pp)
        try:
            doc_date_first = Document.objects.filter(parlperiod=pp).order_by('date').first().date
            print(doc_date_first)
            pp.start_date = doc_date_first
            pp.save()
        except:
            print("start date attribution did not work")
            pass
        try:
            doc_date_last = Document.objects.filter(parlperiod=pp).order_by('date').last().date
            print(doc_date_last)
            pp.end_date = doc_date_last
            pp.save()
        except:
            print("stop date attribution did not work")
            pass

    return 0
