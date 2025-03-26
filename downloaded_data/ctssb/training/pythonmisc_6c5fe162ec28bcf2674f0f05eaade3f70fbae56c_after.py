#!/usr/bin/env python3
import unittest
from sys import stderr

from abc import ABCMeta
from abc import abstractmethod
from os import path
from os import walk
from os.path import basename
from os.path import sep
from re import search
from re import sub

from Bash import bash
from ParallelCommand import ParallelCommand

__all__ = ["PairedEndCommand"]


class PairedEndCommand(ParallelCommand):
    """
    Extension of ParallelCommand to run parallel commands with paired end
    sequencing files, mainly for Illumina data
    Makes small changes to the file gathering and init methods that every
    Paired job needs in order to run
    """
    __metaclass__ = ABCMeta  # Still requires overwrite for make_command

    def __init__(self, *args, **kwargs):
        """
        __init__ Initialize this class with arguments passed to it.

        PairedEndCommand proceeds as follows:
        1) Load environment modules
        2) Gather input files
        3) Remove exclusions from input files
        4) Make output directories
        5) Format commands based on make_command method
        6) Send commands to wrapper for cluster scheduler using options
        7) Unload environment modules

        Expected positional args:
            None

        Expcected kwargs:
            Unique to PairedEndCommand
                :param: read_regex: str: regex for first of the paired end files

            :param: input_root: str: the input root
            :param: output_root: str: the output root
            :param: input_regex: str: regex specifying all input files
            :param: extension: str: regex for extension on files
            :param: exclusions: str: regex or python list that specifies which
                    files are to be excluded from the input files of this run
            :param: exlcusions_paths: str: directory path or comma-separated
                    list of directory names that each contain files with a
                    basename that you wish for this class to skip during run()
                    that should be excluded from the given run
            :param: dry_run: bool: Toggles whether or not commands are actually
                    run
            :param: verbose: bool: Toggles print statements throughout class
            :param: cluster_options: dict<str>: dictionary of cluster options
                memory - The memory to be allocated to this job
                nodes - The nodes to be allocated
                cpus - The cpus **per node** to request
                partition -  The queue name or partition name for the submitted
                job
                job_name - common prefix for all jobs created by this instance
                depends_on - The dependencies (as comma separated list of job
                numbers)
                email_address -  The email address to use for notifications
                email_options - Email options: BEGIN|END|FAIL|ABORT|ALL
                time - time to request from the scheduler
                bash -  The bash shebang line to use in the script


        Any other keyword arguments will be added as an attribute with that name
        to the instance of this class. So, if additional parameters are needed
        for formatting commands or any other overriden methods, then they
        can be specified as a keyword agument to init for convenience.

        For example, map.py uses a --stats flag to determine whether or
        not the user wants to output mapping statistics alongside the mapping.

        Many commands use a reference genome or some additional data files, you
        could specify these by adding --reference="reference.fa" to the input
        and then invoking "self.reference" in the make_command method.
        """
        super(PairedEndCommand, self).__init__(*args, **kwargs)
        self.set_default('read_regex', "_R1")
        self.set_default("tmp_dir", "~/tmp")

    def mate(self, read):
        """
        Return the filename of the mate for this read, based on read_regex
        :param: read: str: the read filename
        :return: str: substituted string
        :raises: AttributeError: thrown by not finding a match ro the rege
        """
        try:
            read_match = search(self.read_regex, read).group(0)
            mate_match = sub("1", "2", read_match)  # Ex: _R1_ --> _R2_
            return (sub(read_match, mate_match, read))  # whole read name
        except AttributeError as err:  # Nonetype has no attribute group
            raise (err)

    def __replace_regex(self, regex, replacement, string):
        """
        Replace regex in a string with a replacement string
        :param: regex: str: the regular expression to replace
        :param: replacement: str: replacement string
        :param: string: str: the string in which to make the replacement
        :return: str: string with replacement substituted
        :raises: AttributeError: when a match is not found for regex in string
        """
        try:
            match = search(regex, string).group(0)
            return (sub(match, replacement, string))
        except AttributeError as err:  # Nonetype object has no attribute group
            raise (err)

    def replace_read_marker_with(self, replacement, read):
        """
        Replace the read_regex wtih some replacement. Calls __replace_regex,
        using regex=self.read_regex to make the replacement
        :param replacement: str: replacement string
        :param read: str: the string to make replacements in
        :return: str: read with replacement in the place of read_regex matches
        :raises: AttributeError: from __replace_regex, if match not found
        """
        return self.__replace_regex(self.read_regex, replacement, read)

    def replace_extension_with(self, extension, read):
        """
        Replace the extention of "read" with the new "extension"
        :param extension: str: new file extension
        :param read: str: putattive file name to replace extension in
        :return: read with its last extension replaced with the new extension
        """
        try:
            return (self.__replace_regex(self.extension, extension, read))
        except AttributeError:  # Did not find a match for self.extension
            # Replace last extension with new one, if no previous extensions,
            # then just adds the new one to the end of the basename
            return (read.rsplit(".", 1)[0] + extension)

    def exclude_files_below(self, root):
        """
        Remove files that are below the directory named by root from input
        :param root: str: assumed to be a directory containing files to remove
        """
        if type(root) is list:  # Assume python list of filenames
            for directory in root:  # for each assumed string in list
                self.exclude_files_below(directory)  # recall this method

        if "," in root:  # Okay, so everything here is not a python list, but
            for directory in root.split(","):  # may contain ',', so for each
                self.exclude_files_below(directory)  # recall this method

        exclusions = []  # will hold final list of exclusions

        if path.isdir(root):  # If string is a accessible directory
            if self.verbose:
                print("Removing files from {}".format(root), file=stderr)

            for root, dir, files in walk(root):  # Walk this directory
                for filename in files:  # for each filename found
                    base = basename(filename)  # get its basename
                    base_no_ext = path.splitext(base)[0]  # strip extensions
                    exclusions += [base_no_ext]  # add basename to exclusions
                    try:
                        # Since this might be the output directory of a
                        # previous run for this command, search for any files
                        # that have a "_pe" in their name, and replace with
                        # the default read marker, then add this to the list
                        possible_input = self.__replace_regex("_pe", "_R1",
                                                              base_no_ext)
                        exclusions += [possible_input]
                    except AttributeError:  # Did not match, but that's alright
                        pass

                    try:
                        # Try this process again with another common read marker
                        possible_input = self.__replace_regex("_pe", "_1",
                                                              base_no_ext)
                        exclusions += [possible_input]
                    except AttributeError:  # No match
                        pass

        for regex in list(set(exclusions)):  # For each unique basename
            self.remove_regex_from_input(regex)  # remove it from the input

    def get_read_groups(self, filename):
        lib = "lib"
        platform = "illumina"
        sample = "sample"
        barcode = "XXXX"
        lane = 1

        if search("_L[0-9]{3}", filename):
            sample = filename.split("_L")[0]
        elif search("_R[1|2]", filename):
            sample = filename.split("_R")[0]
        else:
            sample = filename

        display_filename = "cat {}".format(filename)

        if filename.endswith(".gz"):
            display_filename = "gunzip -c {}".format(filename)

        command = ("{} | head -n 10000 | grep ^@ | cut -d':' -f10 | tr -d ' ' "
                   "| sort | uniq -c | sort -nr | head -1 | sed -e "
                   "'s/^[[:space:]]*//' | cut -d ' ' -f2").format(
            display_filename)

        try:
            barcode = bash(command)[0].strip()
        except:
            print("Could not determine barcode", file=stderr)

        try:
            lane = int(search("(?<=_L)[0-9].*?(?=_pe)", filename).group(0))
        except AttributeError:
            if self.verbose:
                print("Could not determine lane number", file=stderr)

        platform_unit = "{}.{}".format(barcode, lane)

        split = filename.split(sep)
        if len(split) > 2:
            lib = split[-2]

        return {
            'rglb': lib,
            'rgpl': platform,
            'rgpu': platform_unit,
            'rgsm': sample
        }



    def get_files(self):
        """
        Gather all files that match the input_regex that are below the input
        directory
        :return:
        """
        for root, _, files in walk(self.input_root):
            for filename in files:  # for all files
                # Match input_regex and read_regex in the files found
                if (search(self.input_regex, filename) and
                        search(self.read_regex, filename)):
                    if self.extension is not None:
                        if search(self.extension, filename):
                            abs_path = path.join(root, filename)
                            self.files += [abs_path]

                            if self.verbose:
                                print(abs_path, file=stderr)
                    else:
                        abs_path = path.join(root, filename)
                        self.files += [abs_path]

                        if self.verbose:
                            print(abs_path, file=stderr)

    @abstractmethod
    def make_command(self, filename):
        pass


class TestPairedEndCommand(unittest.TestCase):
    # Some day, I will write these unit tests
    def setUp(self):
        pass

    def test_mate(self):
        pass

    def test_replace_read_marker_with(self):
        pass

    def test_replace_extension(self):
        pass

    def test_get_files(self):
        pass

    def tearDown(self):
        pass


if __name__ == "__main__":
    suite = unittest.TestLoader().loadTestsFromTestCase(TestPairedEndCommand)
    unittest.TextTestRunner(verbosity=3).run(suite)
