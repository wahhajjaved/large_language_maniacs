import numpy
import bz2
import gzip
import copy
import os
import sys
import csv
from collections import OrderedDict
import random
import re
import string

import utils

delimit_info = {'.csv' : ',', '.tsv' : '\t'}

# ----------------------------------------------------------------------------------------
def add_seed_seq(args, input_info, reco_info, is_data):
    input_info[args.seed_unique_id] = {'unique_ids' : [args.seed_unique_id, ], 'seqs' : [args.seed_seq, ]}
    if not is_data:
        reco_info[args.seed_unique_id] = 'unknown!'  # hopefully more obvious than a key error

# ----------------------------------------------------------------------------------------
def post_process(input_info, reco_info, args, infname, found_seed, is_data, iline):
    if args is None:
        return

    if args.istartstop is not None:
        n_lines_in_file = iline + 1
        if n_lines_in_file < args.istartstop[1]:
            raise Exception('--istartstop upper bound %d larger than number of lines in file %d' % (args.istartstop[1], n_lines_in_file))
    if len(input_info) == 0:
        if args.queries is not None and args.seed_seq is None:  # if --seed-seq is specified, we don't expect to pull it from the file
            raise Exception('didn\'t find the specified --queries (%s) in %s' % (str(args.queries), infname))
        if args.reco_ids is not None:
            raise Exception('didn\'t find the specified --reco-ids (%s) in %s' % (str(args.reco_ids), infname))
    if args.queries is not None:
        missing_queries = set(args.queries) - set(input_info)
        if args.seed_seq is not None:  # if the seed uid isn't in the input file, you can specify its sequence with --seed-seq
            missing_queries -= set([args.seed_unique_id])
        extra_queries = set(input_info) - set(args.queries)  # this is just checking for a bug in the code just above here...
        if len(missing_queries) > 0:
            raise Exception('didn\'t find some of the specified --queries: %s' % ' '.join(missing_queries))
        if len(extra_queries) > 0:
            raise Exception('extracted uids %s that weren\'t specified with --queries' % ' '.join(extra_queries))
    if args.seed_unique_id is not None:
        if found_seed:
            if args.seed_seq is not None:  # and input_info[args.seed_unique_id]['seqs'][0] != args.seed_seq:
                # raise Exception('incompatible --seed-unique-id and --seed-seq (i.e. the sequence in %s corresponding to %s wasn\'t %s)' % (infname, args.seed_unique_id, args.seed_seq))
                raise Exception('--seed-seq was specified, but --seed-unique-id was also present in input file')
        else:
            if args.seed_seq is None:
                raise Exception('couldn\'t find seed unique id %s in %s' % (args.seed_unique_id, infname))
            add_seed_seq(args, input_info, reco_info, is_data)
    elif args.seed_seq is not None:
        add_seed_seq(args, input_info, reco_info, is_data)
    elif args.random_seed_seq:  # already checked (in bin/partis) that other seed args aren't set
        args.seed_unique_id = random.choice(input_info.keys())
        print '    chose random seed unique id %s' % args.seed_unique_id

    if args.n_random_queries is not None:
        included_queries = set()  # only for dbg printing
        uids_to_choose_from = input_info.keys()
        if args.seed_unique_id is not None:
            uids_to_choose_from.remove(args.seed_unique_id)
            included_queries.add(args.seed_unique_id)
        if args.queries_to_include is not None:
            for uid in args.queries_to_include:
                if args.seed_unique_id is not None and uid == args.seed_unique_id:
                    continue
                if uid not in uids_to_choose_from:
                    raise Exception('couldn\'t find requested query %s in %s' % (uid, infname))
                uids_to_choose_from.remove(uid)
                included_queries.add(uid)
        if args.n_random_queries >= len(input_info):
            print '  %s --n-random-queries %d >= number of queries read from %s (so just keeping everybody)' % (utils.color('yellow', 'warning'), args.n_random_queries, infname)
        else:
            uids_to_remove = numpy.random.choice(uids_to_choose_from, len(input_info) - args.n_random_queries, replace=False)
            for uid in uids_to_remove:
                del input_info[uid]
                if reco_info is not None:
                    del reco_info[uid]
            print '  --n-random-queries: keeping %d / %d sequences from input file (removed %d%s)' % (len(input_info), len(input_info) + len(uids_to_remove), len(uids_to_remove),
                                                                                                      (' and specifically kept %s' % ' '.join(included_queries)) if len(included_queries) > 0 else '')

# ----------------------------------------------------------------------------------------
def get_seqfile_info(x, is_data=False):
    raise Exception('renamed and changed returned vals (see below)')

# ----------------------------------------------------------------------------------------
def read_sequence_file(infname, is_data, n_max_queries=-1, args=None, simglfo=None, quiet=False):
    # NOTE renamed this from get_seqfile_info() since I'm changing the return values, but I don't want to update the calls everywhere (e.g. in compareutils)
    yaml_glfo = None
    suffix = utils.getsuffix(infname)
    if suffix in delimit_info:
        seqfile = open(infname)  # closes on function exit. no, this isn't the best way to do this
        reader = csv.DictReader(seqfile, delimiter=delimit_info[suffix])
    elif suffix in ['.fa', '.fasta', '.fastx']:
        reader = utils.read_fastx(infname, name_key='unique_ids', seq_key='input_seqs', add_info=False, sanitize=True, n_max_queries=n_max_queries,  # NOTE don't use istarstop kw arg here, 'cause it fucks with the istartstop treatment in the loop below
                                  queries=(args.queries if (args is not None and not args.abbreviate) else None))  # NOTE also can't filter on args.queries here if we're also translating
    elif suffix == '.yaml':
        yaml_glfo, reader, _ = utils.read_yaml_output(infname, n_max_queries=n_max_queries, synth_single_seqs=True, dont_add_implicit_info=True)  # not really sure that long term I want to synthesize single seq lines, but for backwards compatibility it's nice a.t.m.
        if not is_data:
            simglfo = yaml_glfo  # doesn't replace the contents, of course, which is why we return it
    else:
        raise Exception('unhandled file extension %s' % suffix)

    input_info = OrderedDict()
    reco_info = None
    if not is_data:
        reco_info = OrderedDict()
    # already_printed_forbidden_character_warning = False
    n_queries_added = 0
    found_seed = False
    potential_names, used_names = None, None  # for abbreviating
    iname = None  # line number -- used as sequence id if there isn't a name column in the file
    iline = -1
    for line in reader:
        iline += 1
        if args is not None:
            if args.istartstop is not None:
                if iline < args.istartstop[0]:
                    continue
                if iline >= args.istartstop[1]:
                    break
            if args.name_column is not None:
                line['unique_ids'] = line[args.name_column]
                del line[args.name_column]
            if args.seq_column is not None:
                line['input_seqs'] = line[args.seq_column]
                if args.seq_column != 'seqs':  # stupid god damn weird backwards compatibility edge case bullshit
                    del line[args.seq_column]
        if iname is None and 'unique_ids' not in line and 'unique_id' not in line:
            print '  %s: couldn\'t find a name (unique id) column, so using line number as the sequence label (you can set the name column with --name-column)' % (utils.color('yellow', 'warning'))
            iname = 0
        if iname is not None:
            line['unique_ids'] = '%09d' % iname
            iname += 1
        if 'input_seqs' not in line and 'seq' not in line:
            raise Exception('couldn\'t find a sequence column in %s (you can set this with --seq-column)' % infname)
        if suffix != '.yaml':
            utils.process_input_line(line)
        if len(line['unique_ids']) > 1:
            raise Exception('can\'t yet handle multi-seq csv input files')
        uid = line['unique_ids'][0]
        if uid in input_info:
            new_uid = uid
            iid = 2
            while new_uid in input_info:
                new_uid = uid + '-' + str(iid)
                iid += 1
            print '  %s uid %s already read from input file %s, so replacing with new uid %s' % (utils.color('yellow', 'warning'), uid, infname, new_uid)
            uid = new_uid
        if args.timepoint_column is not None:
            uid += '@' + line[args.timepoint_column]
        inseq = line['input_seqs'][0]

        # # it would be nice to check here for forbidden characters (in addition to in the .fa code above), but it's hard because we won't have read the csv properly above if it has them
        # if any(fc in uid for fc in utils.forbidden_characters):
        #     raise Exception('found a forbidden character (one of %s) in sequence id \'%s\'' % (' '.join(["'" + fc + "'" for fc in utils.forbidden_characters]), uid))
        if args is not None:
            if args.abbreviate:  # note that this changes <uid>, but doesn't modify <line>
                uid, potential_names, used_names = utils.choose_new_uid(potential_names, used_names)
            if args.queries is not None and uid not in args.queries:
                continue
            if args.reco_ids is not None and line['reco_id'] not in args.reco_ids:
                continue
            if args.seed_unique_id is not None and uid == args.seed_unique_id:
                found_seed = True

        if uid in input_info:
            raise Exception('found uid \'%s\' twice in input file %s' % (uid, infname))

        if any(c not in utils.alphabet for c in inseq):
            unexpected_chars = set([ch for ch in inseq if ch not in utils.alphabet])
            raise Exception('unexpected character%s %s (not among %s) in input sequence with id %s:\n  %s' % (utils.plural(len(unexpected_chars)), ', '.join([('\'%s\'' % ch) for ch in unexpected_chars]), utils.nukes + utils.ambiguous_bases, uid, inseq))

        # da business
        input_info[uid] = {'unique_ids' : [uid, ], 'seqs' : [inseq, ]}

        if not is_data:
            if 'v_gene' not in line:
                raise Exception('simulation info not found in %s' % infname)
            reco_info[uid] = copy.deepcopy(line)
            if simglfo is not None:
                utils.add_implicit_info(simglfo, reco_info[uid])

        n_queries_added += 1
        if n_max_queries > 0 and n_queries_added >= n_max_queries:
            if not quiet:  # just adding <quiet>, and too lazy to decide what other print statements it should effect, this is the only one I care about right now
                print '  --n-max-queries: stopped after reading %d queries from input file' % len(input_info)
            break

    post_process(input_info, reco_info, args, infname, found_seed, is_data, iline)

    if len(input_info) == 0:
        raise Exception('didn\'t read any sequences from %s' % infname)

    return input_info, reco_info, yaml_glfo
