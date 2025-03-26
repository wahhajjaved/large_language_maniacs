from pprint import pprint
import click
from senseclust.queries import joined, joined_freq
from wikiparse.tables import headword, word_sense
from sqlalchemy.sql import distinct, select
from sqlalchemy.sql.functions import count
from os.path import join as pjoin
from senseclust.wordnet import get_lemma_objs, WORDNETS
from stiff.writers import annotation_comment
from finntk.wordnet.utils import pre_id_to_post
from wikiparse.utils.db import get_session, insert
import wordfreq
from senseclust.tables import metadata, freqs
from senseclust.groupings import gen_groupings
from senseclust.utils import split_line, is_wn_ref
from os.path import basename
import itertools
from nltk.tokenize import word_tokenize
from nltk.corpus import wordnet


@click.group()
def man_clus():
    pass


@man_clus.command()
@click.argument("words", type=click.File('r'))
@click.argument("out_dir")
def gen(words, out_dir):
    """
    Generate unclustered words in OUT_DIR from word list WORDS
    """
    session = get_session()
    for word in words:
        word_pos = word.split("#")[0].strip()
        word, pos = word_pos.split(".")
        assert pos == "Noun"
        with open(pjoin(out_dir, word_pos), "w") as outf:
            # Get Wiktionary results
            results = session.execute(select([
                word_sense.c.sense_id,
                word_sense.c.etymology_index,
                word_sense.c.sense,
                word_sense.c.extra,
            ]).select_from(joined).where(
                (headword.c.name == word) &
                (word_sense.c.pos == "Noun")
            ).order_by(word_sense.c.etymology_index)).fetchall()
            prev_ety = None
            for row in results:
                if prev_ety is not None and row["etymology_index"] != prev_ety:
                    outf.write("\n")
                outf.write("{} # {}\n".format(row["sense_id"], row["extra"]["raw_defn"].strip().replace("\n", " --- ")))
                prev_ety = row["etymology_index"]

            # Get WordNet results
            for synset_id, lemma_objs in get_lemma_objs(word, "n", WORDNETS).items():
                wordnets = {wn for wn, _ in lemma_objs}
                outf.write("\n")
                outf.write("{} # [{}] {}\n".format(pre_id_to_post(synset_id), ", ".join(wordnets), annotation_comment(lemma_objs)))


@man_clus.command()
def add_freq_data():
    """
    Add table of frequencies to DB
    """
    session = get_session()
    metadata.create_all(session().get_bind().engine)
    with click.progressbar(wordfreq.get_frequency_dict("fi").items(), label="Inserting frequencies") as name_freqs:
        for name, freq in name_freqs:
            insert(session, freqs, name=name, freq=freq)
    session.commit()


@man_clus.command()
@click.argument("infs", nargs=-1)
@click.argument("out", type=click.File('w'))
def compile(infs, out):
    """
    Compile manually clustered words in files INFS to OUT as a gold csv ready
    for use by eval
    """
    out.write("manann,ref\n")
    for inf in infs:
        word_pos = basename(inf)
        word = word_pos.split(".")[0]
        idx = 1
        with open(inf) as f:
            for line in f:
                if not line.strip():
                    idx += 1
                else:
                    ref = line.split("#")[0].strip()
                    out.write(f"{word}.{idx:02d},{ref}\n")


@man_clus.command()
@click.argument("inf", type=click.File('r'))
@click.argument("out_dir")
def decompile(inf, out_dir):
    session = get_session()
    for lemma, grouping in gen_groupings(inf):
        with open(pjoin(out_dir, lemma), "w") as outf:
            first = True
            for group_num, synsets in grouping.items():
                if not first:
                    outf.write("\n")
                else:
                    first = False
                for synset in synsets:
                    outf.write(synset)
                    outf.write(" # ")
                    if is_wn_ref(synset):
                        sense = wordnet.of2ss(synset).definition()
                    else:
                        sense = session.execute(select([
                            word_sense.c.sense,
                        ]).select_from(joined).where(
                            (headword.c.name == lemma) &
                            (word_sense.c.sense_id == synset)
                        )).fetchone()["sense"]
                    tokens = word_tokenize(sense)
                    outf.write(" ".join(tokens))
                    outf.write("\n")


@man_clus.command()
@click.argument("inf", type=click.File('r'))
@click.argument("outf", type=click.File('w'))
@click.option('--filter', type=click.Choice(['wn', 'wiki', 'link']))
def filter(inf, outf, filter):
    """
    Filter a gold CSV to filter non-WordNet rows
    """
    assert inf.readline().strip() == "manann,ref"
    outf.write("manann,ref\n")
    if filter in ("wn", "wiki"):
        for line in inf:
            manann, ref = line.strip().split(",")
            if ((filter == "wn") and not is_wn_ref(ref)) or \
                    ((filter == "wiki") and is_wn_ref(ref)):
                continue
            outf.write(line)
    else:
        groups = itertools.groupby((split_line(line) for line in inf), lambda tpl: tpl[0])
        for lemma, group in groups:
            wn_grp = []
            wiki_grp = []
            for tpl in group:
                if is_wn_ref(tpl[2]):
                    wn_grp.append(tpl)
                else:
                    wiki_grp.append(tpl)
            grp_idx = 1
            for _, f1, lid1 in wn_grp:
                for _, f2, lid2 in wiki_grp:
                    if f1 == f2:
                        outf.write(f"{lemma}.{grp_idx:02d}.01,{lid1}\n")
                        outf.write(f"{lemma}.{grp_idx:02d}.01,{lid2}\n")
                    else:
                        outf.write(f"{lemma}.{grp_idx:02d}.01,{lid1}\n")
                        outf.write(f"{lemma}.{grp_idx:02d}.02,{lid2}\n")
                    grp_idx += 1


@man_clus.command()
@click.argument("limit", required=False, type=int)
@click.option("--verbose/--no-verbose")
def pick_words(limit=50, verbose=False):
    """
    Pick etymologically ambigious nouns for creating manual clustering.
    """
    query = select([
            headword.c.name,
            freqs.c.freq,
        ]).select_from(joined_freq).where(
            word_sense.c.etymology_index.isnot(None) &
            (word_sense.c.pos == "Noun") &
            word_sense.c.inflection_of_id.is_(None)
        ).group_by(
            headword.c.id
        ).having(
            count(
                distinct(word_sense.c.etymology_index)
            ) > 1
        ).order_by(freqs.c.freq.desc()).limit(limit)
    session = get_session()
    candidates = session.execute(query).fetchall()
    for word, freq in candidates:
        print(word + ".Noun", "#", freq)
    if verbose:
        print("\n")
        for word, _ in candidates:
            print("#", word)
            pprint(session.execute(select([
                word_sense.c.sense_id,
                word_sense.c.sense,
            ]).select_from(joined).where(
                headword.c.name == word
            )).fetchall())


if __name__ == "__main__":
    man_clus()
