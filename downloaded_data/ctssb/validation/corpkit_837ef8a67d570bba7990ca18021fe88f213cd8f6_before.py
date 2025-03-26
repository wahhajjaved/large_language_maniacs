from __future__ import print_function

def editor(interrogation, 
            operation = None,
            denominator = False,
            sort_by = False,
            keep_stats = False,
            keep_top = False,
            just_totals = False,
            threshold = 'medium',
            just_entries = False,
            skip_entries = False,
            merge_entries = False,
            newname = 'combine',
            just_subcorpora = False,
            skip_subcorpora = False,
            span_subcorpora = False,
            merge_subcorpora = False,
            new_subcorpus_name = False,
            replace_names = False,
            projection = False,
            remove_above_p = False,
            p = 0.05, 
            revert_year = True,
            print_info = False,
            spelling = False,
            selfdrop = True,
            calc_all = True,
            **kwargs
            ):
    """Edit results of interrogations, do keywording, sort, etc.

    ``just/skip_entries`` and ``just/skip_subcorpora`` can take a few different kinds of input:

    * str: treated as regular expression to match
    * list: 

      * of integers: indices to match
      * of strings: entries/subcorpora to match

    ``merge_entries`` and ``merge_subcorpora``, however, are best entered as dicts:

    ``{newname: criteria, newname2: criteria2}```

    where criteria is a string, list, etc.

    :param interrogation: Results to edit
    :type interrogation: pandas.core.frame.DataFrame
    
    :param operation: Kind of maths to do on inputted lists:

        '+', '-', '/', '*', '%': self explanatory
        'k': log likelihood (keywords)
        'a': get distance metric (for use with interrogator 'a' option)
        'd': get percent difference (alternative approach to keywording)

    :type operation: str
    
    :param denominator: List of results or totals.

        If list of results, for each entry in dataframe 1, locate
        entry with same name in dataframe 2, and do maths there
        if 'self', do all merging/keeping operations, then use
        edited interrogation as denominator

    :type denominator: pandas.core.series.Series/pandas.core.frame.DataFrame/dict/'self'
    
    :param sort_by: Calculate slope, stderr, r, p values, then sort by:

        increase: highest to lowest slope value
        decrease: lowest to highest slope value
        turbulent: most change in y axis values
        static: least change in y axis values
        total/most: largest number first
        infreq/least: smallest number first
        name: alphabetically
        
    :type sort_by: str

    :param keep_stats: Keep/drop stats values from dataframe after sorting
    :type keep_stats: bool
    
    :param keep_top: After sorting, remove all but the top *keep_top* results
    :type keep_top: int
    
    :param just_totals: Sum each column and work with sums
    :type just_totals: bool
    
    :param threshold: When using results list as denominator, drop values occurring
                        fewer than n times. If not keywording, you can use:
                            ``'high'``: denominator total / 2500
                            ``'medium'``: denominator total / 5000
                            ``'low'``: denominator total / 10000
                        Note: if keywording, there are smaller default thresholds
    :type threshold: int/bool
    :param just_entries: Keep matching entries
    :type just_entries: see above
    :param skip_entries: Skip matching entries
    :type skip_entries: see above
    :param merge_entries: Merge matching entries
    :type merge_entries: see above
    :param newname: New name for merged entries
    :type newname: str/'combine'
    :param just_subcorpora: Keep matching subcorpora
    :type just_subcorpora: see above
    :param skip_subcorpora: Skip matching subcorpora
    :type skip_subcorpora: see above
    :param span_subcorpora: If subcorpora are numerically named, span all from *int* to *int2*, inclusive
    :type span_subcorpora: tuple -- ``(int, int2)``
    :param merge_subcorpora: Merge matching subcorpora
    :type merge_subcorpora: see above
    :param new_subcorpus_name: Name for merged subcorpora
    :type new_subcorpus_name: str/``'combine'``

    :param replace_names: Edit result names and then merge duplicate names.
    :type replace_names: dict -- ``{criteria: replacement_text}``; str -- a regex to delete from names
    :param projection:         a  to multiply results in subcorpus by n
    :type projection: tuple -- ``(subcorpus_name, n)``
    :param remove_above_p: Delete any result over p
    :type remove_above_p: bool
    :param p:                  set the p value
    :type p: float
    
    :param revert_year:        when doing linear regression on years, turn annual subcorpora into 1, 2 ...
    :type revert_year: bool
    
    :param print_info: Print stuff to console showing what's being edited
    :type print_info: bool
    
    :param spelling: Convert/normalise spelling:
    :type spelling: str -- ``'US'``/``'UK'``
    
    :param selfdrop: When keywording, try to remove target corpus from reference corpus
    :type selfdrop: bool
    
    :param calc_all: When keywording, calculate words that appear in either corpus
    :type calc_all: bool

    :returns: corpkit.interrogation.Interrogation
    """

    # grab arguments, in case we get dict input and have to iterate
    locs = locals()

    import corpkit
    import pandas
    import re
    import collections
    import pandas as pd
    import numpy as np

    from pandas import DataFrame, Series
    from time import localtime, strftime
    
    try:
        get_ipython().getoutput()
    except TypeError:
        have_ipython = True
    except NameError:
        have_ipython = False
    try:
        from IPython.display import display, clear_output
    except ImportError:
        pass

    return_conc = False
    from interrogation import Interrodict, Interrogation, Concordance
    if interrogation.__class__ == Interrodict:
        locs.pop('interrogation', None)
        from collections import OrderedDict
        outdict = OrderedDict()
        from editor import editor
        for i, (k, v) in enumerate(interrogation.items()):
            # only print the first time around
            if i != 0:
                locs['print_info'] = False
            # if df2 is also a dict, get the relevant entry
            if type(denominator) == dict or denominator.__class__ == Interrodict:
                #if sorted(set([i.lower() for i in list(dataframe1.keys())])) == \
                #   sorted(set([i.lower() for i in list(denominator.keys())])):
                #   locs['denominator'] = denominator[k]
                    if kwargs.get('denominator_totals'):
                        locs['denominator'] = denominator[k].totals
                    else:
                        locs['denominator'] = denominator[k].results

            outdict[k] = editor(v.results, **locs)
        if print_info:
            from time import localtime, strftime
            thetime = strftime("%H:%M:%S", localtime())
            print("\n%s: Finished! Output is a dictionary with keys:\n\n         '%s'\n" % (thetime, "'\n         '".join(sorted(outdict.keys()))))
        return Interrodict(outdict)

    elif type(interrogation) in [pandas.core.frame.DataFrame, pandas.core.series.Series]:
        dataframe1 = interrogation
    elif interrogation.__class__ == Interrogation:
        #if interrogation.__dict__.get('concordance', None) is not None:
        #    concordances = interrogation.concordance
        branch = kwargs.pop('branch', 'results')
        if branch.lower().startswith('r') :
            dataframe1 = interrogation.results
        elif branch.lower().startswith('t'):
            dataframe1 = interrogation.totals
        elif branch.lower().startswith('c'):
            dataframe1 = interrogation.concordance
            return_conc = True
        else:
            dataframe1 = interrogation.results
    
    elif interrogation.__class__ == Concordance or \
                        all(x in list(dataframe1.columns) for x in ['l', 'm', 'r']):
            return_conc = True
            dataframe1 = interrogation
    # hope for the best
    else:
        dataframe1 = interrogation

    the_time_started = strftime("%Y-%m-%d %H:%M:%S")

    pd.options.mode.chained_assignment = None

    try:
        from process import checkstack
    except ImportError:
        from corpkit.process import checkstack
        
    if checkstack('pythontex'):
        print_info = False

    def combiney(df, df2, operation = '%', threshold = 'medium', prinf = True):
        """mash df and df2 together in appropriate way"""
        totals = False
        # delete under threshold
        if just_totals:
            if using_totals:
                if not single_totals:
                    to_drop = list(df2[df2['Combined total'] < threshold].index)
                    df = df.drop([e for e in to_drop if e in list(df.index)])
                    if prinf:
                        to_show = []
                        [to_show.append(w) for w in to_drop[:5]]
                        if len(to_drop) > 10:
                            to_show.append('...')
                            [to_show.append(w) for w in to_drop[-5:]]
                        if len(to_drop) > 0:
                            print('Removing %d entries below threshold:\n    %s' % (len(to_drop), '\n    '.join(to_show)))
                        if len(to_drop) > 10:
                            print('... and %d more ... \n' % (len(to_drop) - len(to_show) + 1))
                        else:
                            print('')
                else:
                    denom = df2
        else:
            denom = list(df2)
        if single_totals:
            if operation == '%':
                totals = df.sum() * 100.0 / float(df.sum().sum())
                df = df * 100.0
                try:
                    df = df.div(denom, axis = 0)
                except ValueError:
                    from time import localtime, strftime
                    thetime = strftime("%H:%M:%S", localtime())
                    print('%s: cannot combine DataFrame 1 and 2: different shapes' % thetime)
            elif operation == '+':
                try:
                    df = df.add(denom, axis = 0)
                except ValueError:
                    from time import localtime, strftime
                    thetime = strftime("%H:%M:%S", localtime())
                    print('%s: cannot combine DataFrame 1 and 2: different shapes' % thetime)
            elif operation == '-':
                try:
                    df = df.sub(denom, axis = 0)
                except ValueError:
                    from time import localtime, strftime
                    thetime = strftime("%H:%M:%S", localtime())
                    print('%s: cannot combine DataFrame 1 and 2: different shapes' % thetime)
            elif operation == '*':
                totals = df.sum() * float(df.sum().sum())
                try:
                    df = df.mul(denom, axis = 0)
                except ValueError:
                    from time import localtime, strftime
                    thetime = strftime("%H:%M:%S", localtime())
                    print('%s: cannot combine DataFrame 1 and 2: different shapes' % thetime)
            elif operation == '/':
                try:
                    totals = df.sum() / float(df.sum().sum())
                    df = df.div(denom, axis = 0)
                except ValueError:
                    from time import localtime, strftime
                    thetime = strftime("%H:%M:%S", localtime())
                    print('%s: cannot combine DataFrame 1 and 2: different shapes' % thetime)
            elif operation == 'd':
                #df.ix['Combined total'] = df.sum()
                #to_drop = to_drop = list(df.T[df.T['Combined total'] < threshold].index)
                to_drop = [n for n in list(df.columns) if df[n].sum() < threshold]
                df = df.drop([e for e in to_drop if e in list(df.columns)], axis = 1)
                #df.drop('Combined total')
                if prinf:
                    to_show = []
                    [to_show.append(w) for w in to_drop[:5]]
                    if len(to_drop) > 10:
                        to_show.append('...')
                        [to_show.append(w) for w in to_drop[-5:]]
                    if len(to_drop) > 0:
                        print('Removing %d entries below threshold:\n    %s' % (len(to_drop), '\n    '.join(to_show)))
                    if len(to_drop) > 10:
                        print('... and %d more ... \n' % (len(to_drop) - len(to_show) + 1))
                    else:
                        print('')

                # get normalised num in target corpus
                norm_in_target = df.div(denom, axis = 0)
                # get normalised num in reference corpus, with or without selfdrop
                tot_in_ref = df.copy()
                for c in list(tot_in_ref.index):
                    if selfdrop:
                        tot_in_ref.ix[c] = df.sum() - tot_in_ref.ix[c]
                    else:
                        tot_in_ref.ix[c] = df.sum()
                norm_in_ref = tot_in_ref.div(df.sum().sum())
                df = (norm_in_target - norm_in_ref) / norm_in_ref * 100.0
                df = df.replace(float(-100.00), np.nan)

            elif operation == 'a':
                for c in [c for c in list(df.columns) if int(c) > 1]:
                    df[c] = df[c] * (1.0 / int(c))
                df = df.sum(axis = 1) / df2
            
            elif operation.startswith('c'):
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    df = pandas.concat([df, df2], axis = 1)
            return df, totals

        elif not single_totals:
            if not operation.startswith('a'):
                # generate totals
                if operation == '%':
                    totals = df.sum() * 100.0 / float(df2.sum().sum())
                if operation == '*':
                    totals = df.sum() * float(df2.sum().sum())
                if operation == '/':
                    totals = df.sum() / float(df2.sum().sum())
                if operation.startswith('c'):
                    # add here the info that merging will not work 
                    # with identical colnames
                    import warnings
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        d = pd.concat([df.T, df2.T])
                        # make index nums
                        d = d.reset_index()
                        # sum and remove duplicates
                        d = d.groupby('index').sum()
                        dx = d.reset_index('index')
                        dx.index = list(dx['index'])
                        df = dx.drop('index', axis = 1).T

                def editf(datum):
                    meth = {'%': datum.div,
                            '*': datum.mul,
                            '/': datum.div,
                            '+': datum.add,
                            '-': datum.sub}

                    if datum.name in list(df2.columns):

                        method = meth[operation]
                        mathed = method(df2[datum.name], fill_value = 0.0)
                        if operation == '%':
                            return mathed * 100.0
                        else:
                            return mathed
                    else:
                        return datum * 0.0

                df = df.apply(editf)

            else:
                for c in [c for c in list(df.columns) if int(c) > 1]:
                    df[c] = df[c] * (1.0 / int(c))
                df = df.sum(axis = 1) / df2.T.sum()

        return df, totals

    def parse_input(df, the_input):
        """turn whatever has been passed in into list of words that can 
           be used as pandas indices---maybe a bad way to go about it"""
        parsed_input = False
        import re
        if the_input == 'all':
            the_input = r'.*'
        if type(the_input) == int:
            try:
                the_input = str(the_input)
            except:
                pass
            the_input = [the_input]
        elif type(the_input) == str or type(the_input) == unicode:
            regex = re.compile(the_input)
            parsed_input = [w for w in list(df) if re.search(regex, w)]
            return parsed_input
        from dictionaries.process_types import Wordlist
        if type(the_input) == Wordlist:
            the_input = list(the_input)
        if type(the_input) == list:
            if type(the_input[0]) == int:
                parsed_input = [word for index, word in enumerate(list(df)) if index in the_input]
            elif type(the_input[0]) == str or type(the_input[0]) == unicode:
                try:
                    parsed_input = [word for word in the_input if word in df.columns]
                except AttributeError: # if series
                    parsed_input = [word for word in the_input if word in df.index]
        return parsed_input

    def synonymise(df, pos = 'n'):
        """pass a df and a pos and convert df columns to most common synonyms"""
        from nltk.corpus import wordnet as wn
        #from dictionaries.taxonomies import taxonomies
        from collections import Counter
        fixed = []
        for w in list(df.columns):
            try:
                syns = []
                for syns in wn.synsets(w, pos = pos):
                    for w in syns:
                        synonyms.append(w)
                top_syn = Counter(syns).most_common(1)[0][0]
                fixed.append(top_syn)
            except:
                fixed.append(w)
        df.columns = fixed
        return df

    def convert_spell(df, convert_to = 'US', print_info = print_info):
        """turn dataframes into us/uk spelling"""
        from dictionaries.word_transforms import usa_convert
        if print_info:
            print('Converting spelling ... \n')
        if convert_to == 'UK':
            usa_convert = {v: k for k, v in list(usa_convert.items())}
        fixed = []
        for val in list(df.columns):
            try:
                fixed.append(usa_convert[val])
            except:
                fixed.append(val)
        df.columns = fixed
        return df

    def merge_duplicates(df, print_info = print_info):
        if print_info:
            print('Merging duplicate entries ... \n')
        # now we have to merge all duplicates
        for dup in df.columns.get_duplicates():
            #num_dupes = len(list(df[dup].columns))
            temp = df[dup].sum(axis = 1)
            #df = df.drop([dup for d in range(num_dupes)], axis = 1)
            df = df.drop(dup, axis = 1)
            df[dup] = temp
        return df

    def name_replacer(df, replace_names, print_info = print_info):
        """replace entry names and merge"""
        import re        
        # double or single nest if need be
        if type(replace_names) == str:
            replace_names = [(replace_names, '')]
        if type(replace_names) != dict:
            if type(replace_names[0]) == str:
                replace_names = [replace_names]
        if type(replace_names) == dict:
            replace_names = [(v, k) for k, v in list(replace_names.items())]
        for to_find, replacement in replace_names:
            if print_info:
                try:
                    print('Replacing "%s" with "%s" ...\n' % (to_find, replacement))
                except:
                    print('Deleting "%s" from entry names ...\n' % (to_find))
            to_find = re.compile(to_find)
            try:
                replacement = replacement
            except:
                replacement = ''
            df.columns = [re.sub(to_find, replacement, l) for l in list(df.columns)]
        df = merge_duplicates(df, print_info = False)
        return df

    def just_these_entries(df, parsed_input, prinf = True):
        entries = [word for word in list(df) if word not in parsed_input]
        if prinf:
            print('Keeping %d entries:\n    %s' % (len(parsed_input), '\n    '.join(parsed_input[:10])))
            if len(parsed_input) > 10:
                print('... and %d more ... \n' % (len(parsed_input) - 10))
            else:
                print('')
        df = df.drop(entries, axis = 1)
        return df

    def skip_these_entries(df, parsed_input, prinf = True):
        if prinf:     
            print('Skipping %d entries:\n    %s' % (len(parsed_input), '\n    '.join(parsed_input[:10])))
            if len(parsed_input) > 10:
                print('... and %d more ... \n' % (len(parsed_input) - 10))
            else:
                print('')
        df = df.drop(parsed_input, axis = 1)
        return df

    def newname_getter(df, parsed_input, newname = 'combine', prinf = True, merging_subcorpora = False):
        """makes appropriate name for merged entries"""
        if merging_subcorpora:
            if newname is False:
                newname = 'combine'
        if type(newname) == int:
            the_newname = list(df.columns)[newname]
        elif type(newname) == str or type(newname) == unicode:
            if newname == 'combine':
                if len(parsed_input) <= 3:
                    the_newname = '/'.join(parsed_input)
                elif len(parsed_input) > 3:
                    the_newname = '/'.join(parsed_input[:3]) + '...'
            else:
                the_newname = newname
        if newname is False:
            # revise this code
            import operator
            sumdict = {}
            for item in parsed_input:
                summed = sum(list(df[item]))
                sumdict[item] = summed
            the_newname = max(iter(sumdict.items()), key=operator.itemgetter(1))[0]
        if type(the_newname) not in [str, unicode]:
            the_newname = str(the_newname, errors = 'ignore')
        return the_newname

    def merge_these_entries(df, parsed_input, the_newname, prinf = True, merging = 'entries'):
        # make new entry with sum of parsed input
        if len(parsed_input) == 0:
            import warnings
            warnings.warn('No %s could be automatically merged.\n' % merging)
        else:
            if prinf:
                print('Merging %d %s as "%s":\n    %s' % (len(parsed_input), merging, the_newname, '\n    '.join(parsed_input[:10])))
                if len(parsed_input) > 10:
                    print('... and %d more ... \n' % (len(parsed_input) - 10))
                else:
                    print('')
        # remove old entries
        temp = sum([df[i] for i in parsed_input])

        #if type(merge_entries) == dict and len(merge_entries.keys() > 1):

        if type(df) == pandas.core.series.Series:
            df = df.drop(parsed_input, errors = 'ignore')
            nms = list(df.index)
        else:
            df = df.drop(parsed_input, axis = 1, errors = 'ignore')
            nms = list(df.columns)
        if the_newname in nms:
            df[the_newname] = df[the_newname] + temp
        else:
            df[the_newname] = temp
        return df

    def just_these_subcorpora(df, lst_of_subcorpora, prinf = True):        
        if type(lst_of_subcorpora[0]) == int:
            lst_of_subcorpora = [str(l) for l in lst_of_subcorpora]
        good_years = [subcorpus for subcorpus in list(df.index) if subcorpus in lst_of_subcorpora]
        if prinf:
            print('Keeping %d subcorpora:\n    %s' % (len(good_years), '\n    '.join(good_years[:10])))
            if len(good_years) > 10:
                print('... and %d more ... \n' % (len(good_years) - 10))
            else:
                print('')
        df = df.drop([subcorpus for subcorpus in list(df.index) if subcorpus not in good_years], axis = 0)
        return df

    def skip_these_subcorpora(df, lst_of_subcorpora, prinf = True):
        if type(lst_of_subcorpora) == int:
            lst_of_subcorpora = [lst_of_subcorpora]
        if type(lst_of_subcorpora[0]) == int:
            lst_of_subcorpora = [str(l) for l in lst_of_subcorpora]
        bad_years = [subcorpus for subcorpus in list(df.index) if subcorpus in lst_of_subcorpora]
        if len(bad_years) == 0:
            import warnings
            warnings.warn('No subcorpora skipped.\n')
        else:
            if prinf:       
                print('Skipping %d subcorpora:\n    %s' % (len(bad_years), '\n    '.join([str(i) for i in bad_years[:10]])))
                if len(bad_years) > 10:
                    print('... and %d more ... \n' % (len(bad_years) - 10))
                else:
                    print('')
        df = df.drop([subcorpus for subcorpus in list(df.index) if subcorpus in bad_years], axis = 0)
        return df

    def span_these_subcorpora(df, lst_of_subcorpora, prinf = True):
        """select only a span of numerical suborpora (first, last)"""
        non_totals = [subcorpus for subcorpus in list(df.index)]
        good_years = [subcorpus for subcorpus in non_totals if int(subcorpus) >= int(lst_of_subcorpora[0]) and int(subcorpus) <= int(lst_of_subcorpora[-1])]
        if len(lst_of_subcorpora) == 0:
            import warnings
            warnings.warn('Span not identified.\n')
        else:        
            if prinf:        
                print('Keeping subcorpora:\n    %d--%d\n' % (int(lst_of_subcorpora[0]), int(lst_of_subcorpora[-1])))
        df = df.drop([subcorpus for subcorpus in list(df.index) if subcorpus not in good_years], axis = 0)
        # retotal needed here
        return df

    def projector(df, list_of_tuples, prinf = True):
        """project abs values"""
        if type(list_of_tuples) == list:
            tdict = {}
            for a, b in list_of_tuples:
                tdict[a] = b
            list_of_tuples = tdict
        for subcorpus, projection_value in list(list_of_tuples.items()):
            if type(subcorpus) == int:
                subcorpus = str(subcorpus)
            df.ix[subcorpus] = df.ix[subcorpus] * projection_value
            if prinf:
                if type(projection_value) == float:
                    print('Projection: %s * %s' % (subcorpus, projection_value))
                if type(projection_value) == int:
                    print('Projection: %s * %d' % (subcorpus, projection_value))
        if prinf:
            print('')
        return df

    def do_stats(df):
        """do linregress and add to df"""
        try: 
            from scipy.stats import linregress
        except ImportError:
            from time import localtime, strftime
            thetime = strftime("%H:%M:%S", localtime())
            print('%s: sort type not available in this verion of corpkit.' % thetime)
            return False
        #from stats.stats import linregress

        entries = []
        slopes = []
        intercepts = []
        rs = []
        ps = []
        stderrs = []
        indices = list(df.index)
        first_year = list(df.index)[0]
        try:
            x = [int(y) - int(first_year) for y in indices]
        except ValueError:
            x = list(range(len(indices)))
        statfields = ['slope', 'intercept', 'r', 'p', 'stderr']
        for entry in list(df.columns):
            entries.append(entry)
            y = list(df[entry])
            slope, intercept, r, p, stderr = linregress(x, y)
            slopes.append(slope)
            intercepts.append(intercept)
            rs.append(r)
            ps.append(p)
            stderrs.append(stderr)
        sl = pd.DataFrame([slopes, intercepts, rs, ps, stderrs], 
                           index = statfields, 
                           columns = list(df.columns))
        df = df.append(sl)
        # drop infinites and nans
        if operation != 'd':
            df = df.replace([np.inf, -np.inf], np.nan)
            df = df.fillna(0.0)
        return df

    def recalc(df, operation = '%'):
        statfields = ['slope', 'intercept', 'r', 'p', 'stderr']
        """Add totals to the dataframe1"""

        #df.drop('Total', axis = 0, inplace = True)
        #df.drop('Total', axis = 1, inplace = True)
        try:
            df['temp-Total'] = df.drop(statfields).sum(axis = 1)
        except:
            df['temp-Total'] = df.sum(axis = 1)
        df = df.T
        try:
            df['temp-Total'] = df.drop(statfields).sum(axis = 1)
        except:
            df['temp-Total'] = df.sum(axis = 1)
        df = df.T
        return df

    def resort(df, sort_by = False, keep_stats = False):
        """sort results, potentially using scipy's linregress"""
        
        # translate options and make sure they are parseable
        options = ['total', 'name', 'infreq', 'increase', 'turbulent',
                   'decrease', 'static', 'most', 'least', 'none', 'p']

        if sort_by is True:
            sort_by = 'total'
        if sort_by == 'most':
            sort_by = 'total'
        if sort_by == 'least':
            sort_by = 'infreq'
        if sort_by not in options and sort_by:
            raise ValueError("sort_by parameter error: '%s' not recognised. Must be True, False, %s" % (sort_by, ', '.join(options)))

        if operation.startswith('k'):
            if type(df) == pandas.core.series.Series:
                if sort_by == 'total':
                    df = df.order(ascending = False)

                elif sort_by == 'infreq':
                    df = df.order(ascending = True)

                elif sort_by == 'name':
                    df = df.sort_index()
                return df

        if just_totals:
            if sort_by == 'infreq':
                df = df.sort_values(by = 'Combined total', ascending = True, axis = 1)
            elif sort_by == 'total':
                df = df.sort_values(by = 'Combined total', ascending = False, axis = 1)
            elif sort_by == 'name':
                df = df.sort_index()
            return df

        # this is really shitty now that i know how to sort, like in the above
        if keep_stats:
            df = do_stats(df)
            if type(df) == bool:
                if df is False:
                    return False
        if sort_by == 'total':
            if df1_istotals:
                df = df.T
            df = recalc(df, operation = operation)
            tot = df.ix['temp-Total']
            df = df[tot.argsort()[::-1]]
            df = df.drop('temp-Total', axis = 0)
            df = df.drop('temp-Total', axis = 1)
            if df1_istotals:
                df = df.T
        elif sort_by == 'infreq':
            if df1_istotals:
                df = df.T
            df = recalc(df, operation = operation)
            tot = df.ix['temp-Total']
            df = df[tot.argsort()]
            df = df.drop('temp-Total', axis = 0)
            df = df.drop('temp-Total', axis = 1)
            if df1_istotals:
                df = df.T
        elif sort_by == 'name':
            # currently case sensitive...
            df = df.reindex_axis(sorted(df.columns), axis=1)
        elif sort_by == 'p':
            df = df.T.sort_values(by='p').T
        else:
            statfields = ['slope', 'intercept', 'r', 'p', 'stderr']
            
            if not keep_stats:
                df = do_stats(df)
                if type(df) == bool:
                    if df is False:
                        return False

            slopes = df.ix['slope']
            if sort_by == 'increase':
                df = df[slopes.argsort()[::-1]]
            elif sort_by == 'decrease':
                df = df[slopes.argsort()]
            elif sort_by == 'static':
                df = df[slopes.abs().argsort()]
            elif sort_by == 'turbulent':
                df = df[slopes.abs().argsort()[::-1]]
            if remove_above_p:
                # the easy way to do it!
                df = df.T
                df = df[df['p'] <= p]
                df = df.T

            # remove stats field by default
            if not keep_stats:
                df = df.drop(statfields, axis = 0)

        return df

    def set_threshold(big_list, threshold, prinf = True, for_keywords = False):
        if type(threshold) == str:
            if threshold.startswith('l'):
                denominator = 10000
            if threshold.startswith('m'):
                denominator = 5000
            if threshold.startswith('h'):
                denominator = 2500

            if type(big_list) == pandas.core.frame.DataFrame:
                tot = big_list.sum().sum()

            if type(big_list) == pandas.core.series.Series:
                tot = big_list.sum()
            the_threshold = float(tot) / float(denominator)
            #if for_keywords:
                #the_threshold = the_threshold / 2
        else:
            the_threshold = threshold
        if prinf:
            print('Threshold: %d\n' % the_threshold)
        return the_threshold

    # copy dataframe to be very safe
    df = dataframe1.copy()
    # make cols into strings
    try:
        df.columns = [str(c) for c in list(df.columns)]
    except:
        pass

    if operation is None:
        operation = 'None'

    # do concordance work
    if return_conc:
        if just_entries:
            if type(just_entries) == int:
                just_entries = [just_entries]
            if type(just_entries) == str:
                df = df[df['m'].str.contains(just_entries)]
            if type(just_entries) == list:
                if all(type(e) == str for e in just_entries):
                    mp = df['m'].map(lambda x: x in just_entries)
                    df = df[mp]
                else:
                    df = df.ix[just_entries]

        if skip_entries:
            if type(skip_entries) == int:
                skip_entries = [skip_entries]
            if type(skip_entries) == str:
                df = df[~df['m'].str.contains(skip_entries)]
            if type(skip_entries) == list:
                if all(type(e) == str for e in skip_entries):
                    mp = df['m'].map(lambda x: x not in skip_entries)
                    df = df[mp]
                else:
                    df = df.drop(skip_entries, axis = 0)

        if just_subcorpora:
            if type(just_subcorpora) == int:
                just_subcorpora = [just_subcorpora]
            if type(just_subcorpora) == str:
                df = df[df['c'].str.contains(just_subcorpora)]
            if type(just_subcorpora) == list:
                if all(type(e) == str for e in just_subcorpora):
                    mp = df['c'].map(lambda x: x in just_subcorpora)
                    df = df[mp]
                else:
                    df = df.ix[just_subcorpora]

        if skip_subcorpora:
            if type(skip_subcorpora) == int:
                skip_subcorpora = [skip_subcorpora]
            if type(skip_subcorpora) == str:
                df = df[~df['c'].str.contains(skip_subcorpora)]
            if type(skip_subcorpora) == list:
                if all(type(e) == str for e in skip_subcorpora):
                    mp = df['c'].map(lambda x: x not in skip_subcorpora)
                    df = df[mp]
                else:
                    df = df.drop(skip_subcorpora, axis = 0)

        return Concordance(df)

    if print_info:
        print('\n***Processing results***\n========================\n')

    df1_istotals = False
    if type(df) == pandas.core.series.Series:
        df1_istotals = True
        df = pandas.DataFrame(df)
        # if just a single result
    else:
        df = pandas.DataFrame(df)
    if operation.startswith('k'):
        if sort_by is False:
            if not df1_istotals:
                sort_by = 'turbulent'
        if df1_istotals:
            df = df.T
    
    # figure out if there's a second list
    # copy and remove totals if there is
    single_totals = True
    using_totals = False
    outputmode = False

    if denominator.__class__ == Interrogation:
        try:
            denominator = denominator.results
        except AttributeError:
            denominator = denominator.totals

    if denominator is not False and type(denominator) != str:
        df2 = denominator.copy()
        using_totals = True
        if type(df2) == pandas.core.frame.DataFrame:
            if len(df2.columns) > 1:
                single_totals = False
            else:
                df2 = pandas.Series(df2)
            if operation == 'd':
                df2 = df2.sum(axis = 1)
                single_totals = True
        elif type(df2) == pandas.core.series.Series:
            single_totals = True
            #if operation == 'k':
                #raise ValueError('Keywording requires a DataFrame for denominator. Use "self"?')
        else:
            raise ValueError('Denominator not recognised.')
    else:
        if operation in ['k', 'd', 'a', '%', '/', '*', '-', '+']:
            denominator = 'self'         
        if denominator == 'self':
            outputmode = True

    if operation.startswith('a') or operation.startswith('A'):
        if list(df.columns)[0] != '0' and list(df.columns)[0] != 0:
            df = df.T
        if using_totals:
            if not single_totals:
                df2 = df2.T

    if projection:
        # projection shouldn't do anything when working with '%', remember.
        df = projector(df, projection)
        if using_totals:
            df2 = projector(df2, projection)

    if spelling:
        df = convert_spell(df, convert_to = spelling)
        df = merge_duplicates(df, print_info = False)

        if not single_totals:
            df2 = convert_spell(df2, convert_to = spelling, print_info = False)
            df2 = merge_duplicates(df2, print_info = False)
        if not df1_istotals:
            sort_by = 'total'

    if replace_names:
        df = name_replacer(df, replace_names)
        df = merge_duplicates(df)
        if not single_totals:
            df2 = name_replacer(df2, print_info = False)
            df2 = merge_duplicates(df2, print_info = False)
        if not sort_by:
            sort_by = 'total'

    # remove old stats if they're there:
    statfields = ['slope', 'intercept', 'r', 'p', 'stderr']
    try:
        df = df.drop(statfields, axis = 0)
    except:
        pass
    if using_totals:
        try:
            df2 = df2.drop(statfields, axis = 0)
        except:
            pass

    # remove totals and tkinter order
    for name, ax in zip(['Total'] * 2 + ['tkintertable-order'] * 2, [0, 1, 0, 1]):
        if name == 'Total' and df1_istotals:
            continue
        try:
            df = df.drop(name, axis = ax, errors = 'ignore')
        except:
            pass
    for name, ax in zip(['Total'] * 2 + ['tkintertable-order'] * 2, [0, 1, 0, 1]):
        if name == 'Total' and single_totals:
            continue

        try:

            df2 = df2.drop(name, axis = ax, errors = 'ignore')
        except:
            pass

    # merging: make dicts if they aren't already, so we can iterate
    if merge_entries:
        if type(merge_entries) != list:
            if type(merge_entries) == str or type(merge_entries) == str:
                merge_entries = {newname: merge_entries}
            # for newname, criteria    
            for name, the_input in sorted(merge_entries.items()):
                the_newname = newname_getter(df, parse_input(df, the_input), newname = name, prinf = print_info)
                df = merge_these_entries(df, parse_input(df, the_input), the_newname, prinf = print_info)
                if not single_totals:
                    df2 = merge_these_entries(df2, parse_input(df2, the_input), the_newname, prinf = False)
        else:
            for i in merge_entries:
                the_newname = newname_getter(df, parse_input(df, merge_entries), newname = newname, prinf = print_info)
                df = merge_these_entries(df, parse_input(df, merge_entries), the_newname, prinf = print_info)
                if not single_totals:
                    df2 = merge_these_entries(df2, parse_input(df2, merge_entries), the_newname, prinf = False)
    
    if merge_subcorpora:
        if type(merge_subcorpora) != dict:
            if type(merge_subcorpora) == list:
                if type(merge_subcorpora[0]) == tuple:
                    merge_subcorpora = {x: y for x, y in merge_subcorpora}
                elif type(merge_subcorpora[0]) == str or type(merge_subcorpora[0]) == str:
                    merge_subcorpora = {new_subcorpus_name: [x for x in merge_subcorpora]}
                elif type(merge_subcorpora[0]) == int:
                    merge_subcorpora = {new_subcorpus_name: [str(x) for x in merge_subcorpora]}
            else:
                merge_subcorpora = {new_subcorpus_name: merge_subcorpora}
        for name, the_input in sorted(merge_subcorpora.items()):
            the_newname = newname_getter(df.T, parse_input(df.T, the_input), 
                                     newname = name, 
                                     merging_subcorpora = True,
                                     prinf = print_info)
            df = merge_these_entries(df.T, parse_input(df.T, the_input), the_newname, merging = 'subcorpora', prinf = print_info).T
            if using_totals:
                df2 = merge_these_entries(df2.T, parse_input(df2.T, the_input), the_newname, merging = 'subcorpora', prinf = False).T
    
    if just_subcorpora:
        df = just_these_subcorpora(df, just_subcorpora, prinf = print_info)
        if using_totals:
            df2 = just_these_subcorpora(df2, just_subcorpora, prinf = False)
    
    if skip_subcorpora:
        df = skip_these_subcorpora(df, skip_subcorpora, prinf = print_info)
        if using_totals:
            df2 = skip_these_subcorpora(df2, skip_subcorpora, prinf = False)
    
    if span_subcorpora:
        df = span_these_subcorpora(df, span_subcorpora, prinf = print_info)
        if using_totals:
            df2 = span_these_subcorpora(df2, span_subcorpora, prinf = False)

    if just_entries:
        df = just_these_entries(df, parse_input(df, just_entries), prinf = print_info)
        if not single_totals:
            df2 = just_these_entries(df2, parse_input(df2, just_entries), prinf = False)
    
    if skip_entries:
        df = skip_these_entries(df, parse_input(df, skip_entries), prinf = print_info)
        if not single_totals:
            df2 = skip_these_entries(df2, parse_input(df2, skip_entries), prinf = False)

    # drop infinites and nans
    if operation != 'd':
        df = df.replace([np.inf, -np.inf], np.nan)
        df = df.fillna(0.0)

    # make just_totals as dataframe
    just_one_total_number = False
    if just_totals:
        df = pd.DataFrame(df.sum(), columns = ['Combined total'])
        if using_totals:
            if not single_totals:
                df2 = pd.DataFrame(df2.sum(), columns = ['Combined total'])
            else:
                just_one_total_number = True
                df2 = df2.sum()

    tots = df.sum(axis = 1)

    if using_totals or outputmode:
        if not operation.startswith('k'):
            the_threshold = 0
            # set a threshold if just_totals
            if outputmode is True:
                df2 = df.T.sum()
                if not just_totals:
                    df2.name = 'Total'
                else:
                    df2.name = 'Combined total'
                using_totals = True
                single_totals = True
            if just_totals:
                if not single_totals:
                    the_threshold = set_threshold(df2, threshold, prinf = print_info)
            if operation == 'd':
                the_threshold = set_threshold(df2, threshold, prinf = print_info) 
            df, tots = combiney(df, df2, operation = operation, threshold = the_threshold, prinf = print_info)
    
    # if doing keywording...
    if operation.startswith('k'):
        from keys import keywords

        # allow saved dicts to be df2, etc
        try:
            if denominator == 'self':
                df2 = df.copy()
        except TypeError:
            pass
        if type(denominator) == str:
            if denominator != 'self':
                df2 = denominator
    
        else:
            the_threshold = False

        df = keywords(df, df2, 
                      selfdrop = selfdrop, 
                      threshold = threshold, 
                      printstatus = print_info,
                      editing = True,
                      calc_all = calc_all,
                      **kwargs)

        # eh?
        df = df.T
    
    # drop infinites and nans
    if operation != 'd':
        df = df.replace([np.inf, -np.inf], np.nan)
        df = df.fillna(0.0)

    # resort data
    if sort_by or keep_stats:
        df = resort(df, keep_stats = keep_stats, sort_by = sort_by)
        if type(df) == bool:
            if df is False:
                return 'linregress'

    if keep_top:
        if not just_totals:
            df = df[list(df.columns)[:keep_top]]
        else:
            df = df.head(keep_top)

    if just_totals:
        # turn just_totals into series:
        df = pd.Series(df['Combined total'], name = 'Combined total')

    if df1_istotals:
        if operation.startswith('k'):
            try:
                df = pd.Series(df.ix[dataframe1.name])
                df.name = '%s: keyness' % df.name
            except:
                df = df.iloc[0,:]
                df.name = 'keyness' % df.name

    # generate totals branch if not percentage results:
    # fix me
    if df1_istotals or operation.startswith('k'):
        if not just_totals:
            try:
                total = pd.Series(df['Total'], name = 'Total')
            except:
                pass
                total = 'none'
            #total = df.copy()
        else:
            total = 'none'
    else:
        # might be wrong if using division or something...
        try:
            total = df.T.sum(axis = 1)
        except:
            total = 'none'
    
    if type(tots) != pandas.core.frame.DataFrame and type(tots) != pandas.core.series.Series:
        total = df.sum(axis = 1)
    else:
        total = tots

    if type(df) == pandas.core.frame.DataFrame:
        datatype = df.iloc[0].dtype
    else:
        datatype = df.dtype

    # TURN INT COL NAMES INTO STR
    try:
        df.results.columns = [str(d) for d in list(df.results.columns)]
    except:
        pass

    def add_tkt_index(df):
        if type(df) != pandas.core.series.Series:
            df = df.T
            df = df.drop('tkintertable-order', errors = 'ignore', axis = 0)
            df = df.drop('tkintertable-order', errors = 'ignore', axis = 1)
            df['tkintertable-order'] = pd.Series([index for index, data in enumerate(list(df.index))], index = list(df.index))
            df = df.T
        return df

    # while tkintertable can't sort rows
    if checkstack('tkinter'):
        df = add_tkt_index(df)

    if kwargs.get('df1_always_df'):
        if type(df) == pandas.core.series.Series:
            df = pandas.DataFrame(df)

    #outputnames = collections.namedtuple('edited_interrogation', ['query', 'results', 'totals'])
    #output = outputnames(the_options, df, total)

    # delete non-appearing conc lines
    if interrogation.__dict__.get('concordance', None) is None:
        lns = None
    else:
        col_crit = interrogation.concordance['m'].map(lambda x: x in list(df.columns))
        ind_crit = interrogation.concordance['c'].map(lambda x: x in list(df.index))
        lns = interrogation.concordance[col_crit]
        lns = lns.loc[ind_crit]
        lns = Concordance(lns)
    
    output = Interrogation(results = df, totals = total, query = locs, concordance = lns)

    if print_info:
        print('***Done!***\n========================\n')

    return output





