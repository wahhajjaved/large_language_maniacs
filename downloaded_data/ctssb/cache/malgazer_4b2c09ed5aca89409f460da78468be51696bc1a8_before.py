import argparse
import datetime
import time
import os
from hashlib import sha256
from virus_total_apis import IntelApi, PublicApi, PrivateApi
import pandas as pd


def main():
    parser = argparse.ArgumentParser(
        description='Downloads samples from VT Intelligence based upon a query.')
    parser.add_argument('OutputDirectory',
                        help='The output directory for the samples.')
    parser.add_argument('Query',
                        help='The valid VTI query.')
    parser.add_argument("-a", "--apikey",
                        help="Your VT Intelligence API key."
                             "", required=True)
    parser.add_argument("-n", "--number_of_samples",
                        help="The number of files to download."
                             "",
                        type=int, default=10, required=True)

    args = parser.parse_args()

    try:
        os.stat(args.OutputDirectory)
    except:
        os.mkdir(args.OutputDirectory)

    intel_api = IntelApi(args.apikey)
    public_api = PublicApi(args.apikey)
    private_api = PrivateApi(args.apikey)

    downloads = 0
    nextpage = None

    df = pd.DataFrame()

    while downloads <= args.number_of_samples:
        results = None
        while results is None:
            nextpage, results = intel_api.get_hashes_from_search(args.Query, nextpage)
            if results.status_code != 200:
                print("\t\t\tError, retrying...")
                time.sleep(60)
                results = None
            else:
                results = results.json()
        print("Downloading Samples...")

        for hash in results['hashes']:
            if downloads < args.number_of_samples:
                filename = os.path.join(args.OutputDirectory,
                                        hash.upper())
                try:
                    os.stat(args.OutputDirectory)
                except:
                    os.mkdir(args.OutputDirectory)

                print("Downloading {0}".format(hash))
                downloaded = False
                while downloaded is False:
                    response = intel_api.get_file(hash, args.OutputDirectory)
                    print("\tDownloaded {0}".format(hash))
                    print("\tVerifying hash...")
                    expected_hash = hash.upper()
                    dl_hash = sha256_file(filename).upper()

                    if expected_hash != dl_hash:
                        print("**** DOWNLOAD ERROR!  SHA256 Does not match!")
                        print("\tExpected SHA256: {0}".format(expected_hash))
                        print("\tCalculated SHA256: {0}".format(dl_hash))
                        print("\tHave you exceeded your quota?")
                    else:
                        print("\t\tHash verified!")
                        downloads += 1
                        downloaded = True

                file_report = None
                while file_report is None:
                    print("\tDownloading file report...")
                    file_report = public_api.get_file_report(hash)
                    if 'error' in file_report:
                        print("\t\t\tError, retrying...")
                        time.sleep(60)
                        file_report = None
                ds = pd.Series(file_report['results'])
                ds.name = hash.upper()
                df = df.append(ds)
            else:
                break

        if nextpage is None or downloads >= args.number_of_samples:
            break

    now = datetime.datetime.now()
    now_str = "{0}_{1:02}_{2:02}_{3:02}_{4:02}_{5:02}_{6}".format(now.year,
                                                                  now.month,
                                                                  now.day,
                                                                  now.hour,
                                                                  now.minute,
                                                                  now.second,
                                                                  now.microsecond)
    df.to_csv(os.path.join(args.OutputDirectory, "vti_metadata_{0}.csv".format(now_str)))
    print("Downloaded {0} Total Samples".format(downloads))


def sha256_file(filename):
    hasher = sha256()
    with open(filename,'rb') as f:
        buf = f.read()
        hasher.update(buf)
    return hasher.hexdigest()

if __name__ == "__main__":
    main()
