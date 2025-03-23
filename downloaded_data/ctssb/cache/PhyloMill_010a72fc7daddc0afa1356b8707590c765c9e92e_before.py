# from __future__ import print_function
# from __future__ import unicode_literals


def concatenate(alignments, padding_length=0, partitions=None):

    '''
    Concatenate alignments based on the Seq ids; row order does not
    matter. If one alignment contains a Seq id that another one does
    not, gaps will be introduced in place of the missing Seq.

    Args:
        alignments: (tuple, list) Alignments to be concatenated.

        padding_length: Introduce this many gaps between concatenated
            alignments.
    '''

    from Bio import Alphabet
    from Bio.Seq import Seq
    from Bio.SeqRecord import SeqRecord
    from Bio.Align import MultipleSeqAlignment
    if not isinstance(alignments, (list, tuple)):
        raise ValueError('Argument must be a list or a tuple.')
    elif len(alignments) == 1:
        return alignments[0]
    if isinstance(alignments, tuple):
        alignments = list(alignments)
    aln1 = None
    aln2 = None
    if len(alignments) > 2:
        aln2 = alignments.pop()
        result1 = concatenate(alignments=alignments,
                              padding_length=padding_length,
                              partitions=partitions)
        aln1 = result1[0]
        partitions = result1[1]
    elif len(alignments) == 2:
        aln1 = alignments[0]
        aln2 = alignments[1]
    if (not isinstance(aln1, MultipleSeqAlignment) or
            not isinstance(aln2, MultipleSeqAlignment)):
        raise ValueError(
            'Argument must inherit from Bio.Align.MultipleSeqAlignment.')
    alphabet = Alphabet._consensus_alphabet([aln1._alphabet, aln2._alphabet])
    aln1_dict = dict()
    aln2_dict = dict()
    for aln1_s in aln1:
        aln1_dict[aln1_s.id] = aln1_s
    for aln2_s in aln2:
        aln2_dict[aln2_s.id] = aln2_s
    aln1_length = aln1.get_alignment_length()
    aln2_length = aln2.get_alignment_length()
    aln1_gaps = SeqRecord(Seq('-' * aln1_length, alphabet))
    aln2_gaps = SeqRecord(Seq('-' * aln2_length, alphabet))
    padding = SeqRecord(Seq('N' * padding_length, alphabet))

    if not partitions:
        partitions = [(1, aln1_length)]
    partitions.append((1 + aln1_length, padding_length + aln1_length + aln2_length))

    result_seq_list = list()
    for aln1_key in aln1_dict.keys():
        merged_Seq = None
        if aln1_key in aln2_dict:
            merged_Seq = aln1_dict[aln1_key] + padding + aln2_dict[aln1_key]
            merged_Seq.id = aln1_dict[aln1_key].id
            merged_Seq.name = ''
            merged_Seq.description = ''
            aln2_dict.pop(aln1_key)
        else:
            aln1_seq_record = aln1_dict[aln1_key]
            merged_Seq = aln1_seq_record + padding + aln2_gaps
            merged_Seq.id = aln1_seq_record.id
            merged_Seq.name = ''
            merged_Seq.description = ''
        result_seq_list.append(merged_Seq)
    for aln2_seq_record in aln2_dict.values():
        merged_Seq = aln1_gaps + padding + aln2_seq_record
        merged_Seq.id = aln2_seq_record.id
        merged_Seq.name = ''
        merged_Seq.description = ''
        result_seq_list.append(merged_Seq)
    result_alignment = MultipleSeqAlignment(result_seq_list, alphabet)
    result_alignment.sort()
    return((result_alignment, partitions))


def align(records, program, options='', program_executable=''):

    import subprocess
    from StringIO import StringIO
    from Bio import AlignIO
    from Bio import SeqIO
    import shlex

    input_handle = StringIO()
    SeqIO.write(records, input_handle, 'fasta')

    args = None

    options = shlex.split(options)

    if program_executable == '':
        program_executable = program

    if program == 'muscle':
        args = [program_executable, '-quiet'] + options + ['-in', '-', '-out', '-']

    elif program == 'mafft':
        args = [program_executable, '--quiet'] + options + ['-']

    if program == 'clustalo':
        args = [program_executable] + options + ['-i', '-']

    alignment = None

    if args:
        # print(args)
        pipe = subprocess.Popen(
            args=args,
            bufsize=0,
            executable=None,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=None,
            close_fds=False,
            shell=False,
            cwd=None,
            env=None,
            universal_newlines=True,
            startupinfo=None,
            creationflags=0)

        data = pipe.communicate(input=input_handle.getvalue())
        alignment = AlignIO.read(StringIO(data[0]), 'fasta')

    return alignment


def pairwise_identity(

    alignment,
    unknown_letters=set(['N']),
    unknown_id=0.0,
    free_unknowns=True,
    gap_id=0.0,
    free_gaps=True,
    end_gap_id=0.0,
    free_end_gaps=True):

    import sys

    from krpy import kriupac

    if len(alignment) != 2:
        print('Alignment must contain exactly two sequences.')
        sys.exit(1)

    end_gap_letter = '#'
    col_count = alignment.get_alignment_length()

    # Produce a list of string representations of the sequences in alignment.
    # Leading and trailing gaps will be replaced with term_gap_letter.
    aln_seq_str_list = list()
    for aln_seq in alignment:
        aln_str = str(aln_seq.seq)
        aln_str_l_strip = aln_str.lstrip(kriupac.IUPAC_DNA_GAPS_STRING)
        left_gap_count = len(aln_str) - len(aln_str_l_strip)
        aln_str_l_r_strip = aln_str_l_strip.rstrip(kriupac.IUPAC_DNA_GAPS_STRING)
        right_gap_count = len(aln_str_l_strip) - len(aln_str_l_r_strip)
        aln_str_term_gaps = left_gap_count * end_gap_letter + aln_str_l_r_strip + right_gap_count * end_gap_letter
        aln_seq_str_list.append(aln_str_term_gaps)

    # Produce a list of alignment column strings.
    aln_column_str_list = list()
    for col_idx in range(0, col_count):
        aln_column_str = ''
        for aln_seq_str in aln_seq_str_list:
            aln_column_str = aln_column_str + aln_seq_str[col_idx]
        aln_column_str_list.append(aln_column_str)

    # print('--- --- --- --- --- --- --- --- --- --- --- ---')

    score_list = list()
    weights_list = list()

    for col_idx in range(0, col_count):
        col_str = aln_column_str_list[col_idx]

        l1 = col_str[0]
        l2 = col_str[1]

        if l1 in kriupac.IUPAC_DNA_DICT_REVERSE.keys():
            l1 = kriupac.IUPAC_DNA_DICT_REVERSE[l1]

        if l2 in kriupac.IUPAC_DNA_DICT_REVERSE.keys():
            l2 = kriupac.IUPAC_DNA_DICT_REVERSE[l2]

        l1 = set(l1)
        l2 = set(l2)

        #

        end_gap_in_l1 = False
        end_gap_in_l2 = False
        end_gap_in_col = False

        if end_gap_letter in l1:
            end_gap_in_l1 = True
        if end_gap_letter in l2:
            end_gap_in_l2 = True

        if end_gap_in_l1 or end_gap_in_l2:
            end_gap_in_col = True

        #

        gap_in_l1 = False
        gap_in_l2 = False
        gap_in_col = False

        for g in list(kriupac.IUPAC_DNA_GAPS):

            if g in l1:
                gap_in_l1 = True
            if g in l2:
                gap_in_l2 = True

        if gap_in_l1 or gap_in_l2:
            gap_in_col = True

        #

        unknown_in_l1 = False
        unknown_in_l2 = False
        unknown_in_col = False

        for u in list(unknown_letters):

            if u in l1:
                unknown_in_l1 = True
            if u in l2:
                unknown_in_l2 = True

        if unknown_in_l1 or unknown_in_l2:
            unknown_in_col = True

        #

        score = 0.0
        weight = 0.0

        if end_gap_in_col and gap_in_col:
            weight = 0.0

        elif unknown_in_l1 and unknown_in_l2:
            weight = 0.0

        elif not free_end_gaps and end_gap_in_col:
            score = end_gap_id
            weight = 1.0

        elif not free_gaps and gap_in_col:
            score = gap_id
            weight = 1.0

        elif not free_unknowns and unknown_in_col:
            score = unknown_id
            weight = 1.0

        elif (not end_gap_in_col) and (not gap_in_col) and (not unknown_in_col):
            intersection = l1 & l2
            union = l1 | l2
            score = float(len(intersection)) / float(len(union))
            weight = 1.0

        score_list.append(score)
        weights_list.append(weight)

        # print(l1, l2, score, weight)

        # print('--- --- --- --- --- --- --- --- --- --- --- ---')

    pair_id = 0.0
    if sum(weights_list) > 0.0:
        pair_id = sum(score_list) / sum(weights_list)
    # else:
    #     pair_id = 1.0

    # print(pair_id)

    return pair_id


def identity(

    alignment,
    unknown_letters=set(['N']),
    unknown_id=0.0,
    free_unknowns=True,
    gap_id=0.0,
    free_gaps=True,
    end_gap_id=0.0,
    free_end_gaps=True):

    from Bio.Align import MultipleSeqAlignment

    row_count = len(alignment)

    pair_id_list = list()
    done = set()

    for i in range(0, row_count):
        for j in range(0, row_count):

            if i == j:
                continue

            str_1 = str(i)+','+str(j)
            str_2 = str(j)+','+str(i)

            if (str_1 in done) or (str_2 in done):
                continue

            done.add(str_1)
            done.add(str_2)

            # print(str_1)

            aln = MultipleSeqAlignment(records=[alignment[i], alignment[j]])

            pair_id = pairwise_identity(
                alignment=aln,
                unknown_letters=unknown_letters,
                unknown_id=unknown_id,
                free_unknowns=free_unknowns,
                gap_id=gap_id,
                free_gaps=free_gaps,
                end_gap_id=end_gap_id,
                free_end_gaps=free_end_gaps)

            # print(alignment[i].id, alignment[j].id, pair_id)
            if pair_id > 0.0:
                pair_id_list.append(pair_id)

    # print(sum(pair_id_list))
    # print(len(pair_id_list))

    ident = sum(pair_id_list) / len(pair_id_list)

    return ident


def consensus(
    alignment,
    threshold=0.0,
    unknown='N',
    resolve_ambiguities=False):

    from Bio import Seq
    from Bio.Alphabet import generic_dna
    from Bio.Alphabet import generic_rna
    from krpy import krseq
    from krpy import kriupac

    uracil = False

    col_count = alignment.get_alignment_length()
    # row_count = len(alignment)

    cons_str = ''

    for col_idx in range(0, col_count):

        col_str = alignment[:, col_idx]
        col_counts = dict()
        col_counts_expanded = dict()
        col_total = float()
        col_proportions = dict()
        col_cons_set = set()

        # Count bases in column.
        for letter in col_str:

            letter = letter.upper()

            if letter == 'U':
                uracil = True
                letter = 'T'

            if letter not in kriupac.IUPAC_DNA_GAPS:
                col_counts[letter] = col_counts.get(letter, 0) + 1.0

        for k in col_counts.keys():
            if k in kriupac.IUPAC_DNA_DICT_REVERSE:
                for letter in kriupac.IUPAC_DNA_DICT_REVERSE[k]:
                    col_counts_expanded[letter] = col_counts_expanded.get(letter, 0) + col_counts[k]
            else:
                col_counts_expanded[k] = col_counts_expanded.get(k, 0) + col_counts[k]

        for k in col_counts_expanded.keys():
            base_count = col_counts_expanded[k]
            col_total = col_total + base_count

        for k in col_counts_expanded.keys():
            base_count = col_counts_expanded[k]

            base_prop = 0.0
            if col_total > 0.0:
                base_prop = base_count / col_total

            col_proportions[k] = base_prop

        # Keep only the bases that occur at a high enough frequency
        if len(col_proportions) > 0.0 and threshold == 0.0:
            max_prop = max(col_proportions.values())
            if max_prop != 0.0:
                for k in col_proportions.keys():
                    if col_proportions[k] == max_prop:
                        col_cons_set.add(k)
        else:
            for k in col_proportions.keys():
                if col_proportions[k] >= threshold:
                    col_cons_set.add(k)

        if len(col_cons_set) == 0:
            col_cons_set.add(unknown)

        col_cons_list = list(col_cons_set)
        col_cons_list.sort()
        col_str_new = ''.join(col_cons_list)

        if (unknown in col_str_new) and len(col_str_new) > 1:
            col_str_new = col_str_new.replace(unknown, '')

        if ('N' in col_str_new) and len(col_str_new) > 1:
            col_str_new = col_str_new.replace('N', '')

        site = unknown
        if col_str_new == unknown:
            site = unknown
        elif col_str_new == kriupac.IUPAC_DNA_STRING:
            site = unknown
        else:
            site = kriupac.IUPAC_DNA_DICT[col_str_new]

        cons_str = cons_str + site

    if resolve_ambiguities:
        cons_str = krseq.resolve_ambiguities(cons_str)

    alphabet = generic_dna
    if uracil:
        cons_str = cons_str.replace('T', 'U')
        alphabet = generic_rna

    cons_seq = Seq.Seq(cons_str, alphabet)

    ret_value = cons_seq

    return ret_value


def cluster(

    records,
    threshold=0.95,
    unknown='N',
    key='gi',
    aln_program='mafft',
    aln_executable='mafft',
    aln_options='--auto --reorder --adjustdirection',
    seeds=None):

    results_dict = dict()
    consumed_ids = list()
    seed_ids = list()

    records = sorted(records, key=lambda x: len(x.seq), reverse=True)
    records_seeds = records
    if seeds:
        records_seeds = seeds

        for seed_rec in records_seeds:

            key_value = None
            if key == 'accession':
                key_value = seed_rec.id
            elif key == 'gi':
                key_value = seed_rec.annotations['gi']
            elif key == 'description':
                key_value = seed_rec.description
            else:
                key_value = seed_rec.id

            s_id = key_value
            seed_ids.append(s_id)

    for a_rec in records_seeds:

        key_value = None
        if key == 'accession':
            key_value = a_rec.id
        elif key == 'gi':
            key_value = a_rec.annotations['gi']
        elif key == 'description':
            key_value = a_rec.description
        else:
            key_value = a_rec.id

        a_id = key_value

        if not seeds:
            if a_id in consumed_ids:
                continue

        results_dict[a_id] = list()
        if a_id not in consumed_ids:
            results_dict[a_id].append(['+', a_id, '1.0'])
            consumed_ids.append(a_id)

        for b_rec in records:

            key_value = None
            if key == 'accession':
                key_value = b_rec.id
            elif key == 'gi':
                key_value = b_rec.annotations['gi']
            elif key == 'description':
                key_value = b_rec.description
            else:
                key_value = b_rec.id

            b_id = key_value

            if a_id == b_id:
                continue

            if b_id in consumed_ids:
                continue

            aln = align(
                records=[a_rec, b_rec],
                program=aln_program,
                options=aln_options,
                program_executable=aln_executable)

            direction = '+'
            for a in aln:
                # This will only work with MAFFT!
                if a.id.startswith('_R_'):
                    direction = '-'
                    break

            score = pairwise_identity(
                alignment=aln,
                unknown_letters=set(['N']),
                unknown_id=0.0,
                free_unknowns=True,
                gap_id=0.0,
                free_gaps=True,
                end_gap_id=0.0,
                free_end_gaps=True)

            if score >= threshold:
                results_dict[a_id].append([direction, b_id, score])
                consumed_ids.append(b_id)

            # print(a_id, ':', b_id, '=', score)

    # Report unclustered ids
    results_dict['unclustered'] = list()
    for rec in records:

        key_value = None
        if key == 'accession':
            key_value = rec.id
        elif key == 'gi':
            key_value = rec.annotations['gi']
        elif key == 'description':
            key_value = rec.description
        else:
            key_value = rec.id

        rec_id = key_value

        if rec_id not in consumed_ids:
            results_dict['unclustered'].append(['.', rec_id, '0.0'])

    return results_dict


def dereplicate(
    records,
    threshold=0.95,
    unknown='N',
    key='gi',
    aln_program='mafft',
    aln_executable='mafft',
    aln_options='--auto --reorder --adjustdirection'):

    clusters = cluster(
        records=records,
        threshold=threshold,
        unknown=unknown,
        key=key,
        aln_program=aln_program,
        aln_executable=aln_executable,
        aln_options=aln_options,
        seeds=None)

    dereplicated = list()

    for clust_key in clusters.keys():
        for r in records:
            key_value = None
            if key == 'accession':
                key_value = r.id
            elif key == 'gi':
                key_value = r.annotations['gi']
            elif key == 'description':
                key_value = r.description
            else:
                key_value = r.id

            r_id = key_value

            if r_id == clust_key:
                dereplicated.append(r)
                break

    # Should also probably return cluster info, so it is clear which records clustered together
    return dereplicated


def determine_conserved_regions(alignment_file, matrix, window, min_length, cutoff):

    import subprocess
    import csv
    import os

    directory = os.path.split(alignment_file)[0]
    cons_scores = directory + os.path.sep + 'conservation_scores.tsv'

    subprocess.call('score_conservation.py -o '+cons_scores+' -m /usr/local/conservation_code/matrix/'+matrix+'.bla -w '+str(window)+' '+alignment_file, shell=True)

    cons_csv = csv.reader(open(cons_scores, 'rb'), delimiter='\t')

    regions = []
    region = []

    for row in cons_csv:
        if row[0].startswith('#'):
            continue

        pos = int(row[0])+1
        con = float(row[1])

        if con >= float(cutoff):
            region.append([pos,con])
        else:
            if len(region) >= min_length:
                regions.append(region)
            region = []

    if len(region) >= min_length:
        regions.append(region)

    print('There are '+str(len(regions))+' conserved regions.')

    # for region in regions:
    #     print('----------------')
    #     print('There are '+str(len(region))+' residues in this region.')
    #     for position in region:
    #         print(position)

    return regions


def slice_out_conserved_regions(regions, alignment_file, name_prefix, output_dir_path):

    from Bio import AlignIO
    from Bio.Align import MultipleSeqAlignment
    import subprocess
    import os

    # directory = os.path.split(alignment_file)[0]
    directory = output_dir_path.strip(os.path.sep)
    alignment = AlignIO.read(open(alignment_file), "fasta")

    for i in range(0,len(regions)):

        region = regions[i]
        start = region[0][0]-1
        stop = region[-1][0]
        name = name_prefix + str(i+1)
        sliced_alignment = alignment[:,start:stop]
        sliced_alignment_edited = MultipleSeqAlignment(None)

        output_path = directory + os.path.sep + name + '.fasta'

        for record in sliced_alignment:
            if not "-" in str(record.seq):
                sliced_alignment_edited.append(record)

        AlignIO.write(sliced_alignment_edited, output_path, "fasta")
        subprocess.call('usearch -quiet -minseqlength 1 -derep_fulllength '+output_path+' -output '+output_path, shell=True)

        sliced_alignment_new = AlignIO.read(open(output_path), "fasta")

        j=1

        for record in sliced_alignment_new:
            record.id = name+'_'+str(j)
            record.description = ''
            record.name = ''
            j = j+1

        AlignIO.write(sliced_alignment_new, output_path, "fasta")

    return


# if __name__ == '__main__':

    # # Tests

    # import os

    # PS = os.path.sep

    # import krbioio

    # aln = krbioio.read_alignment_file('/Users/karolis/Desktop/aln_11.phy', 'phylip-relaxed')

    # ident = identity(

    #     alignment=aln,
    #     unknown_letters=set(['N']),
    #     unknown_id=0.0,
    #     free_unknowns=True,
    #     gap_id=0.0,
    #     free_gaps=True,
    #     end_gap_id=0.0,
    #     free_end_gaps=True)

    # print(ident)

    # pid = pairwise_identity(

    #     alignment=aln,
    #     unknown_letters=set(['N']),
    #     unknown_id=0.0,
    #     free_unknowns=True,
    #     gap_id=0.0,
    #     free_gaps=True,
    #     end_gap_id=0.0,
    #     free_end_gaps=True)

    # print(pid)

    # cons = consensus(
    #     alignment=aln,
    #     threshold=0.4,
    #     unknown='N',
    #     resolve_ambiguities=False)

    # print(cons)

    # recs = krbioio.read_sequence_file(
    #     file_path='/Users/karolis/Desktop/Actinidia_chinensis__mRNA.gb',
    #     file_format='genbank',
    #     ret_type='list'
    #     )

    # cluster(
    #     records=recs,
    #     threshold=0.99,
    #     unknown='N',
    #     key='gi',
    #     aln_program='mafft',
    #     aln_executable='mafft',
    #     aln_options='--auto --reorder --adjustdirection')
