from __future__ import absolute_import

import os
import urllib

import settings
import util

from client import EpidbClient
from settings import DEEPBLUE_HOST, DEEPBLUE_PORT
from log import log


class ControledVocabulary:
    """
    A Vocabulary has a source which is a file or an URL. It can read cell line
    and antibody entries from the source.
    """
    def __init__(self, fromURL=False):
        self.biosources = []
        self.antibodies = {}

        f = self._load_data(fromURL)
        self._process_data(f)
        f.close()

    def _process_data(self, f):
        """
        parses the data in the provided file and fills the antibody and cell line lists.
        """
        current = None

        for line in f:
            line = line.strip()
            if len(line) == 0 or line[0] == "#":
                continue

            (key, value) = line.split(" ", 1)
            key = key.strip()
            value = value.strip()

            if key == "term":
                # new "term" key finishes the last object
                if current:
                    if current["type"] == "Cell Line":
                        self.biosources.append(current)
                    elif current["type"] == "Antibody":
                        if "_(" not in current["term"]:
                            self.antibodies[current["term"]] = current
                        else:
                            label = current["term"].split("_(")[0]
                            if label not in self.antibodies:
                                self.antibodies[label] = current

                # start a new object
                current = {
                    "term": value
                }

            # normalize key
            if key == "targetDescription":
                key = "description"

            current[key] = value.strip()

        # add very last object
        if current:
            if current["type"] == "Cell Line":
                self.biosources.append(current)
            elif current["type"] == "Antibody" and "_(" not in current["term"]:
                self.antibodies[current["term"]] = current


    def _load_data(self, from_url):
        """
        retrieves the file from the filesystem or URL and returns it
        """
        if from_url:
            f = urllib.urlopen(settings.VOCAB_URL)
        else:
            f = file(os.path.join(settings.DATA_DIR, "cv/cv.ra"))
        return f


def _adjust_sample_fields(sample):

    new_sample = {
        "term": sample["term"]
    }

    if "karyotype" in sample:
        new_sample["karyotype"] = sample["karyotype"]

    if "lab" in sample:
        new_sample["lab"] = sample["lab"]

    if "organism" in sample:
        new_sample["organism"] = sample["organism"]

    if "sex" in sample and sample["sex"] != "U":
        new_sample["sex"] = sample["sex"]

    if "tier" in sample:
        new_sample["tier"] = sample["tier"]

    if "age" in sample and sample["age"] != "ageUnknown":
        new_sample["age"] = sample["age"]

    if "strain" in sample and sample["strain"] != "Unknown":
        new_sample["strain"] = sample["strain"]

    if "description" in sample:
        new_sample["description"] = sample["description"]

    if "tissue" in sample:
        new_sample["tissue"] = sample["description"]

    if "lineage" in sample and sample["lineage"] != "missing":
        new_sample["lineage"] = sample["lineage"]

    if "childOf" in sample:
        new_sample["childOf"] = sample["childOf"]

    if new_sample["organism"] == "human":
        new_sample["source"] = "ENCODE"
    elif new_sample["organism"] == "mouse":
        new_sample["source"] = "Mouse ENCODE"

    return new_sample


_datasource_name_adjustments = [
    [["H7-hESC"], "embryonic stem cell"],
    [["HVMF", "MEF"], "fibroblast"],
    [["Mel_2183"], "melanoma cell line"],
    [["Olf_neurosphere"], "neuronal stem cell"],
    [["Pons_OC"], "brain"],
    [["Urothelia"], "urothelial cell"],
    [["EpiSC-5", "EpiSC-7"], "epidermal stem cell"],
    [["ES-46C", "ES-CJ7", "ES-D3", "ES-E14", "ES-EM5Sox17huCD25", "ES-TT2", "ES-WW6",
      "ES-WW6_F1KO", "ZhBTc4"], "embryonic stem cell"]
]


def _adjust_datasource_name(biosource):
    for i in range(0, len(_datasource_name_adjustments)):
        if biosource in _datasource_name_adjustments[i][0]:
            return _datasource_name_adjustments[i][1]
    return biosource


def insert_sample(i, user_key):
    epidb = EpidbClient(DEEPBLUE_HOST, DEEPBLUE_PORT)

    sample_fields = _adjust_sample_fields(i)
    biosource_name = sample_fields["term"]

    print(sample_fields)

    if epidb.is_biosource(biosource_name, user_key)[0] == 'okay':
        (s, s_id) = epidb.add_sample(biosource_name, sample_fields, user_key)
        if util.has_error(s, s_id, []):
            log.error("(term) Error while creating sample from the given biosource term: "
                      "%s %s", s_id, biosource_name)
            print sample_fields
    elif "tissue" in i and epidb.is_biosource(i["tissue"], user_key)[0] == 'okay':
        (s, s_id) = epidb.add_sample(i["tissue"], sample_fields, user_key)
        print s, s_id
        if util.has_error(s, s_id, []):
            log.error("(tissue) Error while creating sample from the given biosource term: "
                      "%s %s", s_id, biosource_name)
            print i["tissue"]
            print sample_fields
    # Manual check
    else:
        new_biosource_name = _adjust_datasource_name(biosource_name)
        if not new_biosource_name == biosource_name:
            (s, s_id) = epidb.add_sample(new_biosource_name, sample_fields, user_key)
            if util.has_error(s, s_id, []):
                log.error("Error while creating sample for this term: %s", biosource_name)
                print sample_fields
        else:
            print "Invalid term ", biosource_name, "Please, check the ENCODE CV and include this term."


def manual_curation(user_key):
    epidb = EpidbClient(DEEPBLUE_HOST, DEEPBLUE_PORT)

    print epidb.set_biosource_synonym("MEL cell line", "MEL", user_key)  # "http://www.ebi.ac.uk/efo/EFO_0003971"
    print epidb.set_biosource_synonym("CH12.LX", "CH12", user_key)  # "http://www.ebi.ac.uk/efo/EFO_0005233"
    print epidb.set_biosource_synonym("hippocampus", "brain hippocampus", user_key)
    print epidb.add_biosource("embryonic lung", "", {"SOURCE": "MPI internal"}, user_key)
    print epidb.add_biosource("chordoma", "Neoplasm arising from cellular remnants of the notochord; cancer",
                              {"SOURCE": "MPI internal"}, user_key)
    print epidb.set_biosource_synonym("induced pluripotent stem cell", "induced pluripotent cell (iPS)", user_key)
    print epidb.set_biosource_synonym("neuron", "neurons", user_key)  # CL0000540
    print epidb.set_biosource_synonym("enucleate erythrocyte", "enucleated erythrocyte", user_key)

    # Cerebrum_frontal_OC
    print epidb.add_biosource("frontal cerebrum", "", {"SOURCE": "MPI internal"}, user_key)
    print epidb.set_biosource_parent("cerebrum", "frontal cerebrum", user_key)


def ensure_vocabulary(user_key):
    """
    ensure_vocabulary retrieves a set of cell line and antibody vocabulary and
    adds them to Epidb.
    Note: This method should be called initially. Datasets with unknown vocabulary
    will be rejected by Epidb.
    """
    epidb = EpidbClient(DEEPBLUE_HOST, DEEPBLUE_PORT)

    voc = ControledVocabulary()
    log.info("adding %d biosource to the vocabulary", len(voc.biosources))
    log.info("adding %d antibodies to the vocabulary", len(voc.antibodies))

    # add biosources to epidb
    for cl in voc.biosources:
        insert_sample(cl, user_key)

    # add antibodies to epidb
    for ab in voc.antibodies:
        antibody = voc.antibodies[ab]
        log.debug("(Encode) Inserting epigenetic_mark %s", antibody["target"])
        (s, em_id) = epidb.add_epigenetic_mark(antibody["target"], antibody["description"], user_key=user_key)
        if util.has_error(s, em_id, ["105001"]):
            print "(ENCODE CV Error 8): ", em_id

    log.info("vocabulary added successfully")


_antibodyToTarget = {
    "H3K36me3B": "H3K36me3",
    "PLU1": "KDM5B",
    "p300": "EP300",
    "P300": "EP300",
    "JMJD2A": "KDM4A",
    "CBP": "CREBBP",
    "Pol2(b)": "POLR2A",
    "JARID1A": "KDM5A",
    "NCoR": "NCOR1",
    "LSD1": "KDM1A",
    "NSD2": "WHSC1",
    "PCAF": "KAT2B",
    "H3K4me3B": "H3K4me3",
    "H3K9acB": "H3K9ac",
    "H3K27me3B": "H3K27me3",
    "c-Jun": "JUN",
    "c-Myb": "MYB",
    "c-Myc": "MYC",
    "COREST": "RCOR1",
    "GCN5": "KAT2A",
    "MyoD": "MYOD1",
    "Myogenin": "MYOG",
    "NELFe": "RDBP",
    "Nrf2": "GABPA",
    "NRSF": "REST",
    "Pol2": "POLR2A",
    "Pol2-4H8": "POLR2A",
    "Pol2(phosphoS2)": "POLR2A",
    "UBF": "UBTF",
    "ZNF-MIZD-CP1": "ZMIZ1",
    "RevXlinkChromatin": "Control",
    "ERRA": "ESRRA",
    "AP-2gamma": "TFAP2C",
    "ERalpha_a": "ESR1",
    "AP-2alpha": "TFAP2A",
    "BAF155": "SMARCC1",
    "BAF170": "SMARCC2",
    "Brg1": "SMARCA4",
    "CDP": "CUX1",
    "GABP": "GABPA",
    "GR": "NR3C1",
    "Ini1": "SMARCB1",
    "NFKB": "RELA",
    "PAX5-C20": "PAX5",
    "PAX5-N19": "PAX5",
    "PGC1A": "PPARGC1A",
    "PU.1": "SPI1",
    "Pol3": "POLR3G",
    "SPT20": "FAM48A",
    "TBLR1": "TBL1XR1",
    "TCF7L2_C9B9": "TCF7L2",
    "TFIIIC-110": "GTF3C2",
    "TR4": "NR2C2",
    "WHIP": "WRNIP1",
    "c-Fos": "FOS"
}

def antibodyToTarget(antibody):
    """Returns the target-name for an antibody-name used in ENCODE"""
    if antibody in _antibodyToTarget:
        return _antibodyToTarget[antibody]
    else:
        return None