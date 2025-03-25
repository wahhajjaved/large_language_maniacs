# Utilities Module
import os
import re
import time
import shutil
import pickle
import gzip
import csv
import pandas as pd
import numpy as np
from .files import FileObject
from tsfresh import extract_features, select_features, extract_relevant_features
from tsfresh.utilities.dataframe_functions import impute
from tsfresh.feature_extraction import EfficientFCParameters


class Utils(object):

    translate_classifications = {
        'Trj': 'Trojan',
        'PUP': 'PUA',
        'Adw': 'Adware',
        'Drp': 'Dropper',
        'Wrm': 'Worm',
        'Cryp': 'Ransomware',
        'PUA': 'PUA',
    }

    def __init__(self):
        super(Utils, self).__init__()

    @staticmethod
    def batch_running_window_entropy(in_directory=None,
                                     out_directory=None,
                                     window_sizes=[256],
                                     normalize=True,
                                     skipcalculated=False):
        """
        Calculates the running window entropy of a directory containing
        malware samples that is named from their SHA256 value.  It will
        skip all other files.

        :param in_directory:  The input directory for malware.
        :param out_directory: The output directory for calculated data.
        :param window_sizes: A list of window sizes to calculate.
        :param normalize: Set to False to not normalize.
        :param skipcalculated: Set to True to skip already calculated samples.
        :return: Nothing
        """
        if in_directory is None or out_directory is None:
            raise ValueError('Input and output directories must be real.')
        if len(window_sizes) < 1:
            raise ValueError('Specify a window size in a list.')

        print("Starting running window entropy batch processing for malware samples...")

        # Test to make sure the input directory exists, will throw exception
        # if it does not exist.
        os.stat(in_directory)

        # Start the timer
        start_time = time.time()

        # The RE for malware files with sha256 as the name.
        malware_files_re = re.compile('[a-z0-9]{64}',
                                      flags=re.IGNORECASE)
        samples_processed = 0
        for root, dirs, files in os.walk(in_directory):
            for file in files:
                if malware_files_re.match(file):
                    # Start the timer
                    start_load_time = time.time()

                    print("Input file: {0}".format(file))
                    subdir = root[len(in_directory):]

                    # Create the DB file name...
                    datadir = os.path.join(out_directory, subdir)
                    picklefile = os.path.join(datadir, file) + ".pickle.gz"

                    # Create the directory if needed...
                    try:
                        os.stat(datadir)
                    except:
                        os.makedirs(datadir)

                    if os.path.exists(picklefile) \
                            and os.path.isfile(picklefile) \
                            and not skipcalculated:
                        # Create the malware file name...
                        malwarepath = os.path.join(root, file)
                        m = FileObject.read(picklefile)

                        print("\tCalculating: {0} Type: {1}".format(m.malware.filename, m.malware.filetype))
                        print("\tSaving data to {0}".format(picklefile))

                        # Calculate the entropy of the file...
                        fileentropy = m.entropy(normalize)

                        # Calculate the window entropy for malware samples...
                        if window_sizes is not None:
                            # Iterate through the window sizes...
                            for w in window_sizes:
                                if w < m.malware.file_size:
                                    if w not in m.malware.runningentropy.entropy_data:
                                        print("\t\tCalculating window size {0:,}".format(w))

                                        # Calculate running entropy...
                                        rwe = m.running_entropy(w, normalize)
                                    else:
                                        print("\t\tWindow already exists!")

                            # Write the running entropy...
                            m.write(picklefile)
                    elif not (os.path.exists(picklefile) and skipcalculated):
                        # Create the malware file name...
                        malwarepath = os.path.join(root, file)
                        try:
                            m = FileObject(malwarepath)
                        except:
                            continue

                        print("\tCalculating: {0} Type: {1}".format(m.malware.filename, m.malware.filetype))
                        print("\tSaving data to {0}".format(picklefile))

                        # Remove old pickle files...
                        if os.path.exists(picklefile):
                            os.remove(picklefile)

                        # Calculate the entropy of the file...
                        fileentropy = m.entropy(normalize)

                        # Calculate the window entropy for malware samples...
                        if window_sizes is not None:
                            # Iterate through the window sizes...
                            for w in window_sizes:
                                if w < m.malware.file_size:
                                    print("\t\tCalculating window size {0:,}".format(w))

                                    # Calculate running entropy...
                                    rwe = m.running_entropy(w, normalize)

                            # Write the running entropy...
                            m.write(picklefile)
                    else:
                        print("\t\tSkipping calculation...")

                    print("\tElapsed time {0:.6f} seconds".format(round(time.time() - start_load_time, 6)))

                    samples_processed += 1
                    print("{0:,} samples processed...".format(samples_processed))
        print("Total elapsed time {0:.6f} seconds".format(round(time.time() - start_time, 6)))
        print("{0:,} total samples processed...".format(samples_processed))

    @staticmethod
    def batch_preprocess_rwe_data(in_directory = None,
                                  datapoints = 512,
                                  window_size = 256):
        """
        Return rwe of malware in a dataframe.

        :param in_directory:  The directory containing the malware pickle files
        created in with the batch function above.
        :param datapoints: The number of datapoints to resample RWE.
        :param window_size:  The window size of the RWE, that must be already
        calculated.
        :return:  A Pandas dataframe containing the rwe.
        """
        print("Starting batch processing of running window entropy for malware samples...")
        # Keep track so we don't duplicate work
        processed_sha256 = []

        # Start the timer
        start_time = time.time()
        # Check to see that the input directory exists, this will throw an
        # exception if it does not exist.
        os.stat(in_directory)
        # Only find pickle malware files created by the batch function above.
        malware_files_re = re.compile('[a-z0-9]{64}.pickle.gz',
                                      flags=re.IGNORECASE)
        df = pd.DataFrame()
        samples_processed = 0
        for root, dirs, files in os.walk(in_directory):
            for file in files:
                if malware_files_re.match(file):
                    start_load_time = time.time()
                    print("Reading file: {0}".format(file))
                    f = FileObject.read(os.path.join(root, file))
                    if f.malware.sha256.upper() not in processed_sha256:
                        running_entropy = f.malware.runningentropy

                        if window_size in running_entropy.entropy_data:
                            # Reduce RWE data points
                            xnew, ynew = running_entropy.resample_rwe(window_size=window_size,
                                                                      number_of_data_points=datapoints)
                            s = pd.Series(ynew)
                            s.name = f.malware.sha256.upper()
                            df = df.append(s)
                            processed_sha256.append(f.malware.sha256.upper())
                            print("\tElapsed time {0:.6f} seconds".format(
                                 round(time.time() - start_load_time, 6)))
                            samples_processed += 1
                            print("{0:,} samples processed...".format(
                                 samples_processed))
                        else:
                            print(
                                "ERROR: Window size {0} not in this pickle file!".format(window_size))
        print("Total elapsed time {0:.6f} seconds".format(
              round(time.time() - start_time, 6)))
        print("{0:,} total samples processed...".format(samples_processed))
        return df

    @staticmethod
    def batch_tsfresh_rwe_data(in_directory=None,
                               datapoints=512,
                               window_size=256):
        """
        Return extracted features of malware using tsfresh.

        :param in_directory:  The directory containing the malware pickle files
        created in with the batch function above.
        :param datapoints: The number of datapoints to resample RWE.
        :param window_size:  The window size of the RWE, that must be already
        calculated.
        :return:  A Pandas dataframe containing the tsfresh features, and the
        raw data frame as a tuple.
        """
        print("Starting batch processing of tsfresh on running window entropy for malware samples...")

        # Keep track so we don't duplicate work
        processed_sha256 = []

        # Start the timer
        start_time = time.time()
        # Check to see that the input directory exists, this will throw an
        # exception if it does not exist.
        os.stat(in_directory)
        # Only find pickle malware files created by the batch function above.
        malware_files_re = re.compile('[a-z0-9]{64}.pickle.gz',
                                      flags=re.IGNORECASE)
        df = pd.DataFrame(columns=['id', 'offset', 'rwe'])
        samples_processed = 0
        for root, dirs, files in os.walk(in_directory):
            for file in files:
                if malware_files_re.match(file):
                    start_load_time = time.time()
                    print("Reading file: {0}".format(file))
                    f = FileObject.read(os.path.join(root, file))
                    if f.malware.sha256.upper() not in processed_sha256:
                        running_entropy = f.malware.runningentropy
                        if window_size in running_entropy.entropy_data:
                            # Reduce RWE data points
                            xnew, ynew = running_entropy.resample_rwe(window_size=window_size,
                                                                      number_of_data_points=datapoints)
                            # Create dataframe
                            d = pd.DataFrame(columns=['id', 'offset', 'rwe'])
                            d['rwe'] = ynew
                            d['id'] = f.malware.sha256.upper()
                            d['offset'] = np.arange(0, datapoints)
                            df = df.append(d, ignore_index=True)
                            processed_sha256.append(f.malware.sha256.upper())
                            print("\tElapsed time {0:.6f} seconds".format(
                            round(time.time() - start_load_time, 6)))
                            samples_processed += 1
                            print("{0:,} samples processed...".format(samples_processed))
                        else:
                            print("ERROR: Window size {0} not in this pickle file!".format(window_size))
        print("Calculating TSFresh Features...")
        start_tsfresh_time = time.time()
        settings = EfficientFCParameters()
        extracted_features = extract_features(df,
                                              column_id="id",
                                              column_sort='offset',
                                              default_fc_parameters=settings,
                                              impute_function=impute)
        print("\tElapsed time {0:.6f} seconds".format(
            round(time.time() - start_tsfresh_time, 6)))
        print("Total elapsed time {0:.6f} seconds".format(
            round(time.time() - start_time, 6)))
        print("{0:,} total samples processed...".format(samples_processed))
        return extracted_features, df

    @staticmethod
    def extract_tsfresh_relevant_features(extracted_features, classifications):
        """
        Return only relevant features.

        :param extracted_features:  A dataframe from the tsfresh rwe function
        above.
        :param classifications:  A list of ordered classifications for the features.
        :return:  A DataFrame of relevant features.
        """
        impute(extracted_features)
        features_filtered = select_features(extracted_features, classifications)
        return features_filtered

    @staticmethod
    def get_classifications_from_path(in_directory=None):
        """
        Loads classifications from key words in the path.

        :param in_directory:  This is the directory containing batch processed
        samples with the batch function above (results are pickled).
        :return: A DataFrame with an index of the sha256 and the value of
        the classification guessed from the full path name.
        """
        print("Starting classifications from path for malware samples...")

        # Keep track so we don't duplicate work
        processed_sha256 = []

        df = pd.DataFrame(columns=['classification'])

        # Check to see that the input directory exists, this will throw an
        # exception if it does not exist.
        os.stat(in_directory)
        # The RE for malware files with sha256 as the name.
        malware_files_re = re.compile('[a-z0-9]{64}',
                                      flags=re.IGNORECASE)
        samples_processed = 0
        for root, dirs, files in os.walk(in_directory):
            for file in files:
                if malware_files_re.match(file):
                    samples_processed += 1

                    f = FileObject.read(os.path.join(root, file))

                    if f.malware.sha256.upper() not in processed_sha256:
                        classified = ""
                        if "encrypted" in root.lower():
                            classified = "Encrypted"
                        elif "unpacked" in root.lower():
                            classified = "Unpacked"
                        elif "packed" in root.lower():
                            classified = "Packed"
                        else:
                            classified = ""

                        if "malware" in root.lower():
                            classified += "-Malware"
                        elif "pup" in root.lower():
                            classified += "-PUP"
                        elif "trusted" in root.lower():
                            classified += "-Trusted"
                        else:
                            classified += ""

                        d = dict()
                        d['classification'] = classified
                        ds = pd.Series(d)
                        ds.name = f.malware.sha256.upper()
                        df = df.append(ds)

                        processed_sha256.append(f.malware.sha256.upper())

                        samples_processed += 1
        return df

    @staticmethod
    def parse_classifications_from_path(classifications):
        """
        Parses the classifications from guessed classifications from the paths.

        :param classifications:  A dataframe holding the guessed classifications.
        :return:  The parsed classifications, as a DataFrame.
        """
        cls = pd.DataFrame(columns=['classification'])
        for index, row in classifications.iterrows():
            cl = row[0]
            c = cl.split('-')
            d = dict()
            # d['classification'] = cl
            d['classification'] = c[1]
            ds = pd.Series(d)
            ds.name = index
            cls = cls.append(ds)
        return cls

    @staticmethod
    def estimate_vt_classifications_from_csv(filename, products=None):
        """
        Reads a CSV containing VT classifications and attempts to estimate
        the accurate classification from several AV vendors.

        :param filename:  The file name of the CSV containing the VT data.
        :param products:  The list of products (columns) to use in the classification.
        The order is important.  Products earlier in the list take precedence over
        products later in the list.
        :return:  A DataFrame with the classification for each hash.
        """
        df = pd.read_csv(filename, index_col=0)
        return Utils.estimate_vt_classifications_from_DataFrame(df, products)

    @staticmethod
    def estimate_vt_classifications_from_DataFrame(classifications, products=None):
        """
        Reads a DataFrame containing VT classifications and attempts to estimate
        the accurate classification from several AV vendors.

        :param classifications:  The file name of the CSV containing the VT data.
        :param products:  The list of products (columns) to use in the classification.
        The order is important.  Products earlier in the list take precedence over
        products later in the list.
        :return:  A DataFrame with the classification for each hash.
        """
        if products is None:
            products = ['Microsoft', 'Symantec', 'Kaspersky',
                        'Sophos', 'TrendMicro', 'ClamAV']

        classifications_prods = dict()

        for product in products:
            classifications_prods[product] = Utils.parse_vt_classifications(classifications,
                                                                            product)

        out_df = pd.DataFrame(columns=['classification'])

        translate_classifications = {k.lower(): v for k, v
                                         in Utils.translate_classifications.items()}

        for index, row in classifications.iterrows():
            current_classification = None
            for product in products:
                class_df = classifications_prods[product]
                c = class_df.loc[index]
                c = c['classification']
                if (c is not None
                        and c.lower() != 'none'
                        and c.strip() != ''
                        and current_classification is None):
                    current_classification = c
            if current_classification is not None:
                for string in translate_classifications:
                    if string in c.lower():
                        current_classification = translate_classifications[string]
                        break
                d = dict()
                d['classification'] = current_classification
                ds = pd.Series(d)
                ds.name = index
                out_df = out_df.append(ds)
        return out_df

    @staticmethod
    def parse_vt_classifications(classifications, column_name):
        """
        Parses the classifications from a VT data set

        :param classifications:  The VT data set as a DataFrame.
        :param column_name:  Which column to parse in the DataFrame.
        :return: A DataFrame with the classifications, None if error.
        """
        cls = pd.DataFrame(columns=['classification'])
        for index, row in classifications.iterrows():
            if index not in cls.index:
                if column_name == 'Microsoft':
                    c = Utils.parse_microsoft_classification(row['Microsoft'])
                elif column_name == "Symantec":
                    c = Utils.parse_symantec_classification(row['Symantec'])
                elif column_name == "Kaspersky":
                    c = Utils.parse_kaspersky_classification(row['Kaspersky'])
                elif column_name == "Sophos":
                    c = Utils.parse_sophos_classification(row['Sophos'])
                elif column_name == "TrendMicro":
                    c = Utils.parse_trendmicro_classification(row['TrendMicro'])
                elif column_name == "K7AntiVirus":
                    c = Utils.parse_k7antivirus_classification(row['K7AntiVirus'])
                elif column_name == "ClamAV":
                    c = Utils.parse_clamav_classification(row['ClamAV'])
                elif column_name == "F-Prot":
                    c = Utils.parse_fprot_classification(row['F-Prot'])
                elif column_name == "Avast":
                    c = Utils.parse_avast_classification(row['Avast'])
                elif column_name == "Ikarus":
                    c = Utils.parse_ikarus_classification(row['Ikarus'])
                elif column_name == "Jiangmin":
                    c = Utils.parse_jiangmin_classification(row['Jiangmin'])
                elif column_name == "Emsisoft":
                    c = Utils.parse_generic_classification(row['Emsisoft'])
                elif column_name == "BitDefender":
                    c = Utils.parse_generic_classification(row['BitDefender'])
                elif column_name == "Arcabit":
                    c = Utils.parse_generic_classification(row['Arcabit'])
                elif column_name == "Ad-Aware":
                    c = Utils.parse_generic_classification(row['Ad-Aware'])
                elif column_name == "AVware":
                    c = Utils.parse_generic_classification(row['AVware'])
                elif column_name == "ALYac":
                    c = Utils.parse_generic_classification(row['ALYac'])
                elif column_name == "AVG":
                    c = Utils.parse_avg_classification(row['AVG'])
                elif column_name == "ZoneAlarm":
                    c = Utils.parse_generic_classification(row['ZoneAlarm'])
                elif column_name == "Zillya":
                    c = Utils.parse_generic_classification(row['Zillya'])
                elif column_name == "Yandex":
                    c = Utils.parse_generic_classification(row['Yandex'])
                elif column_name == "ViRobot":
                    c = Utils.parse_generic_classification(row['ViRobot'])
                elif column_name == "VIPRE":
                    c = Utils.parse_generic_classification(row['VIPRE'])
                elif column_name == "VBA32":
                    c = Utils.parse_generic_classification(row['VBA32'])
                elif column_name == "Webroot":
                    c = Utils.parse_webroot_classification(row['Webroot'])
                else:
                    # This is an error, so return None
                    return None
                d = dict()
                d['classification'] = c
                ds = pd.Series(d)
                ds.name = index
                cls = cls.append(ds)
        return cls

    @staticmethod
    def parse_microsoft_classification(classification):
        """
        Parses the classification from a Microsoft VT string

        :param classification:  The VT string
        :return: The classification, or None if it could not parse.
        """
        if isinstance(classification, str):
            if classification == 'scan_error':
                return None
            try:
                c = classification.split(':')
                return c[0]
            except:
                pass
        return None

    @staticmethod
    def parse_symantec_classification(classification):
        """
        Parses the classification from a Symantec VT string

        :param classification:  The VT string
        :return: The classification, or None if it could not parse.
        """
        if isinstance(classification, str):
            if classification == 'scan_error':
                return None
            try:
                c = classification.split('.')
                if c[0] != 'W32':
                    c = c[0].split(' ')
                    c = c[0].split('!')
                    c = c[0].split('@')
                    return c[0]
                else:
                    c = c[1].split('!')
                    c = c[0].split('@')
                    return c[0]
            except:
                pass
        return None

    @staticmethod
    def parse_kaspersky_classification(classification):
        """
        Parses the classification from a Kaspersky VT string

        :param classification:  The VT string
        :return: The classification, or None if it could not parse.
        """
        if isinstance(classification, str):
            if classification == 'scan_error':
                return None
            try:
                c = classification.split('.')
                c = c[0].split(':')
                if len(c) > 1:
                    return c[1]
                else:
                    return c[0]
            except:
                pass
        return None

    @staticmethod
    def parse_sophos_classification(classification):
        """
        Parses the classification from a Sophos VT string

        :param classification:  The VT string
        :return: The classification, or None if it could not parse.
        """
        if isinstance(classification, str):
            if classification == 'scan_error':
                return None
            try:
                if "(pua)" in classification.lower():
                    return classification
                else:
                    c = classification.split('/')
                    return c[1]
            except:
                pass
        return None

    @staticmethod
    def parse_trendmicro_classification(classification):
        """
        Parses the classification from a TrendMicro VT string

        :param classification:  The VT string
        :return: The classification, or None if it could not parse.
        """
        if isinstance(classification, str):
            if classification == 'scan_error':
                return None
            try:
                c = classification.split('_')
                return c[0]
            except:
                pass
        return None

    @staticmethod
    def parse_k7antivirus_classification(classification):
        """
        Parses the classification from a K7AntiVirus VT string

        :param classification:  The VT string
        :return: The classification, or None if it could not parse.
        """
        if isinstance(classification, str):
            if classification == 'scan_error':
                return None
            try:
                c = classification.split(' ')
                return c[0]
            except:
                pass
        return None

    @staticmethod
    def parse_clamav_classification(classification):
        """
        Parses the classification from a ClamAV VT string

        :param classification:  The VT string
        :return: The classification, or None if it could not parse.
        """
        if isinstance(classification, str):
            if classification == 'scan_error':
                return None
            try:
                c = classification.split('.')
                return c[1]
            except:
                pass
        return None

    @staticmethod
    def parse_avast_classification(classification):
        """
        Parses the classification from a Avast VT string

        :param classification:  The VT string
        :return: The classification, or None if it could not parse.
        """
        if isinstance(classification, str):
            if classification == 'scan_error':
                return None
            try:
                c = classification.split(':')
                c = c[1].split(' ')
                return c[0]
            except:
                pass
        return None

    @staticmethod
    def parse_fprot_classification(classification):
        """
        Parses the classification from an F-Prot VT string

        :param classification:  The VT string
        :return: The classification, or None if it could not parse.
        """
        if isinstance(classification, str):
            if classification == 'scan_error':
                return None
            try:
                c = classification.split('/')
                c = c[1].split('.')
                c = c[0].split('!')
                return c[0]
            except:
                pass
        return None

    @staticmethod
    def parse_ikarus_classification(classification):
        """
        Parses the classification from an Ikarus VT string

        :param classification:  The VT string
        :return: The classification, or None if it could not parse.
        """
        if isinstance(classification, str):
            if classification == 'scan_error':
                return None
            try:
                c = classification.split('.')
                return c[0]
            except:
                pass
        return None

    @staticmethod
    def parse_jiangmin_classification(classification):
        """
        Parses the classification from a Jiangmin VT string

        :param classification:  The VT string
        :return: The classification, or None if it could not parse.
        """
        if isinstance(classification, str):
            if classification == 'scan_error':
                return None
            try:
                c = classification.split('.')
                return c[0]
            except:
                pass
        return None

    @staticmethod
    def parse_webroot_classification(classification):
        """
        Parses the classification from a Webroot VT string

        :param classification:  The VT string
        :return: The classification, or None if it could not parse.
        """
        if isinstance(classification, str):
            if classification == 'scan_error':
                return None
            try:
                c = classification.split('.')
                return c[1]
            except:
                pass
        return None

    @staticmethod
    def parse_avg_classification(classification):
        """
        Parses the classification from an AVG VT string

        :param classification:  The VT string
        :return: The classification, or None if it could not parse.
        """
        if isinstance(classification, str):
            if classification == 'scan_error':
                return None
            try:
                class_re = re.compile('.*\[(.*)\].*',
                                       flags=re.IGNORECASE)
                m = class_re.match(classification)
                if m:
                    c = m.group(1)
                    return c
                else:
                    c = classification.split(':')
                    c = c[1]
                    c = c.split(' ')
                    return c[0]
            except:
                pass
        return None

    @staticmethod
    def parse_generic_classification(classification):
        """
        Parses the classification from a generic VT string

        :param classification:  The VT string
        :return: The classification, or None if it could not parse.
        """
        if isinstance(classification, str):
            if classification == 'scan_error':
                return None
            try:
                c = classification.split('.')
                if c[0].lower() == 'gen:variant':
                    c = c[1]
                elif c[0].lower() == 'gen:win32':
                    c = c[1]
                elif c[0].lower() == 'application':
                    c = c[1]
                elif c[0].lower() == 'win32':
                    c = c[1]
                elif c[0].lower() == 'behaveslike':
                    c = c[2]
                else:
                    c = c[0]
                c = c.split(' ')[0]
                if ':' in c:
                    c = c.split(':')[1]
                return c
            except:
                pass
        return None

    @staticmethod
    def parse_classifications_with_delimiter(classifications,
                                             column_name,
                                             delimiter,
                                             split_index=1):
        """
        Parses the classification from a DF where the format is:
        <CLASSIFICATION><DELIMITER><SUBCLASSIFICATION>...

        :param classifications:  The DataFrame containing classification info.
        The DF must have the index as the file hash.
        :param delimiter: the delimiter for the original classification info in
        the DataFrame.
        :param column_name: The column name containing the classification info.
        :param split_index:  The index after the split using the delimiter
        :return: A DataFrame of classifications for hashes.
        """
        cls = pd.DataFrame(columns=['classification'])
        for index, row in classifications.iterrows():
            if isinstance(row[column_name], str):
                cl = row[column_name]
                c = cl.split(delimiter)
                d = dict()
                d['classification'] = c[split_index]
                ds = pd.Series(d)
                ds.name = index
                cls = cls.append(ds)
        return cls

    @staticmethod
    def save_processed_tsfresh_data(raw_data,
                                    classifications,
                                    extracted_features,
                                    datadir):
        """
        Saves the pieces of data that were calculated with the functions above
        to a data directory.

        :param raw_data:  The raw data loaded from the malware sample set.
        :param classifications:  A DataFrame with index of sha256 and
        value of classifications.
        :param extracted_features:  The TSFresh extracted features data.
        :param datadir: The data directory to store the data.  Any old data
        will be deleted!
        :return:  Nothing
        """
        print("Starting the data save for the tsfresh data for malware samples...")
        # Remove previous data
        try:
            shutil.rmtree(datadir)
        except:
            pass
        os.makedirs(datadir)
        if raw_data is not None:
            # Raw data
            raw_data.to_csv(os.path.join(datadir, "raw_data.csv.gz"), compression='gzip')
            with gzip.open(os.path.join(datadir, "raw_data.pickle.gz"), 'wb') as file:
                pickle.dump(raw_data, file)
        if classifications is not None:
            # Classifications
            classifications.to_csv(os.path.join(datadir, "classifications.csv.gz"), compression='gzip')
            with gzip.open(os.path.join(datadir, "classifications.pickle.gz"), 'wb') as file:
                pickle.dump(classifications, file)
        if extracted_features is not None:
            # Extracted Features
            extracted_features.to_csv(os.path.join(datadir, 'extracted_features.csv.gz'),
                                      compression='gzip')
            with gzip.open(os.path.join(datadir, "extracted_features.pickle.gz"), 'wb') as file:
                pickle.dump(extracted_features, file)

    @staticmethod
    def load_processed_tsfresh_data(datadir):
        """
        Loads the data saved from tsfresh.

        :param datadir:  The data directory that contains the data.
        :return:  raw_data, classifications, extracted_features tuple
        """
        # Check to see that the data directory exists, this will throw an
        # exception if it does not exist.
        os.stat(datadir)
        df = None
        try:
            with gzip.open(os.path.join(datadir, "raw_data.pickle.gz"), 'rb') as file:
                df = pickle.load(file)
        except:
            pass
        classifications = None
        try:
            with gzip.open(os.path.join(datadir, "classifications.pickle.gz"), 'rb') as file:
                classifications = pickle.load(file)
        except:
            pass
        extracted_features = None
        try:
            with gzip.open(os.path.join(datadir, "extracted_features.pickle.gz"), 'rb') as file:
                extracted_features = pickle.load(file)
        except:
            pass
        return df, classifications, extracted_features

    @staticmethod
    def save_preprocessed_data(raw_data,
                               classifications,
                               datadir):
        """
        Saves the pieces of data that were calculated with the functions above
        to a data directory.

        :param raw_data:  The raw data loaded from the malware sample set.
        :param classifications:  A DataFrame with index of sha256 and
        value of classifications.
        :param datadir: The data directory to store the data.  Any old data
        will be deleted!
        :return:  Nothing
        """
        print("Starting the data save for the preprocessed data for malware samples...")
        # Remove previous data
        try:
            shutil.rmtree(datadir)
        except:
            pass
        os.makedirs(datadir)
        if raw_data is not None:
            # Raw data
            raw_data.to_csv(os.path.join(datadir, "raw_data.csv.gz"), compression='gzip')
            with gzip.open(os.path.join(datadir, "raw_data.pickle.gz"), 'wb') as file:
                pickle.dump(raw_data, file)
        if classifications is not None:
            # Classifications
            classifications.to_csv(os.path.join(datadir, "classifications.csv.gz"), compression='gzip')
            with gzip.open(os.path.join(datadir, "classifications.pickle.gz"), 'wb') as file:
                pickle.dump(classifications, file)

    @staticmethod
    def load_preprocessed_data(datadir):
        """
        Loads the data saved from preprocessing.

        :param datadir:  The data directory that contains the data.
        :return:  raw_data, classifications tuple
        """
        # Check to see that the data directory exists, this will throw an
        # exception if it does not exist.
        os.stat(datadir)
        df = None
        try:
            with gzip.open(os.path.join(datadir, "raw_data.pickle.gz"), 'rb') as file:
                df = pickle.load(file)
        except:
            pass
        classifications = None
        try:
            with gzip.open(os.path.join(datadir, "classifications.pickle.gz"), 'rb') as file:
                classifications = pickle.load(file)
        except:
            pass
        if classifications is None:
            try:
                classifications = pd.read_csv(os.path.join(datadir, 'classifications.csv'), index_col=0)
            except:
                pass
        return df, classifications
