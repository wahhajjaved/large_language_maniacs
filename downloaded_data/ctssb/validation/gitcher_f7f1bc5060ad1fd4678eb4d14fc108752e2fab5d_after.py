# -*- coding: utf-8 -*-


"""gitcher main

gitcher is a git profile switcher. It facilitates the switching
between git profiles, importing configuration settings such
as name, email and user signatures.
"""

import os
import readline
import sys

from validate_email import validate_email
from prettytable import PrettyTable

from gitcher import model_layer, dictionary
from gitcher.completer import TabCompleter
from gitcher.prof import Prof
from gitcher.not_found_prof_error import NotFoundProfError

# Authorship
__author__ = 'Borja González Seoane'
__copyright__ = 'Copyright 2019, Borja González Seoane'
__credits__ = 'Borja González Seoane'
__license__ = 'LICENSE'
__version__ = '0.4b0'
__maintainer__ = 'Borja González Seoane'
__email__ = 'dev@glezseoane.com'
__status__ = 'Development'

# Prompt styles
COLOR_BLUE = '\033[94m'
COLOR_BRI_BLUE = '\033[94;1m'
COLOR_CYAN = '\033[96m'
COLOR_BRI_CYAN = '\033[96;1m'
COLOR_GREEN = '\033[92m'
COLOR_RED = '\033[91m'
COLOR_YELLOW = '\033[93m'
COLOR_BOLD = '\033[1m'
COLOR_RST = '\033[0m'  # Restore default prompt style

# Predefined messages
MSG_OK = "[" + COLOR_GREEN + "OK" + COLOR_RST + "]"
MSG_ERROR = "[" + COLOR_RED + "ERROR" + COLOR_RST + "]"
MSG_WARNING = "[" + COLOR_YELLOW + "WARNING" + COLOR_RST + "]"


# ===============================================
# =             Auxiliary functions             =
# ===============================================

# noinspection PyShadowingNames
def print_prof_error(profname: str) -> None:
    """Function that prints a nonexistent gitcher profile error.

    :param profname: Name of the gitcher profile to operate with
    :type profname: str
    :return: None, print function
    """
    print(MSG_ERROR + " Profile {0} not exists. Try again...".format(profname))


def raise_order_format_error(arg: str = None) -> None:
    """Function that prints a command line format error advise and raises an
    exception. If arg is not specified, the function prints a complete order
    format error. If yes, raises an error advising the concrete argument
    implicated.

    :param arg: Implicated argument
    :type arg: str
    :return: None, print function
    :raise SyntaxErrorr: Raise error by a bad order compose.
    """
    if arg is not None:
        adv = "Check param {0} syntax!".format(arg)
        print(MSG_ERROR + " " + adv)
    else:
        adv = "Check order syntax composition!"
        print(MSG_ERROR + " " + adv)
    sys.exit(adv)


def print_prof_list() -> None:
    """Function that prints the gitcher profile list.

    :return: None, print function
    """
    cprof = model_layer.model_recuperate_git_current_prof()  # Current profile
    profs = model_layer.model_recuperate_profs()
    if profs:  # If profs is not empty
        profs_table = PrettyTable(['Prof', 'Name', 'Email',
                                   'GPG key', 'Autosign'])
        for prof in profs:
            row = prof.tpl()
            if prof.equivalent(cprof):
                row = [(COLOR_CYAN + profeat + COLOR_RST) for profeat in row]
                row[0] = row[0] + "*"
            profs_table.add_row(row)

        print(profs_table)
        print("*: current in use gitcher profile.")
    else:
        print("No gitcher profiles saved yet. Use 'a' option to add one.")


def listen(text: str, autocompletion_context: [str] = None) -> str:
    """Function that listen an user input, validates it, checks if it not a
    escape command (if it is, exits) and then canalize message to caller
    function. This function also provides the support for autocompletion. To
    use it, its neccesary to pass as second param the context list of keys
    against match.

    :param text: Name of the gitcher profile to operate with
    :type text: str
    :param autocompletion_context: List of keys against match text to
        autocompletion
    :type autocompletion_context: [str]
    :return: User reply after canalize question via 'input()' function.
    :rtype: str
    """
    if autocompletion_context:
        # Init autocompletion support
        readline.set_completer_delims('\t')
        readline.parse_and_bind("tab: complete")
        completer = TabCompleter()
        # Set context properly autocompletion set
        completer.create_list_completer(autocompletion_context)
        readline.set_completer(completer.completer_list)

    reply = input(text).strip()

    if autocompletion_context:  # Clean autocompletion set
        # noinspection PyUnboundLocalVariable
        completer.create_list_completer([])
        readline.set_completer(completer.completer_list)

    try:
        check_syntax(reply)
        if check_opt(reply, escape=True):
            print(COLOR_BLUE + "Bye!" + COLOR_RST)
            sys.exit(0)
    except SyntaxError:
        listen(text)  # Recursive loop to have a valid value
    return reply


def yes_or_no(question: str) -> bool:
    """Function that requires a yes or no answer

    :param question: Yes or no question to the user
    :type question: str
    :return: User reply
    :rtype: bool
    """
    reply = str(listen(question + " (y|n): ")).lower().strip()
    if reply[0] == 'y':
        return True
    if reply[0] == 'n':
        return False
    else:
        print(MSG_ERROR + " Enter (y|n) answer...")
        yes_or_no(question)


def check_syntax(arg: str) -> None:
    """Check strings syntax. Gitcher does not avoid to use commas ','
    in string values.

    :param arg: Argument to check syntax
    :type arg: str
    :return: True or false
    :rtype: bool
    :raise SyntaxError: If arg is illegal
    """
    if ',' in arg:  # The comma (',') is an illegal char
        print(MSG_ERROR + " Do not use commas (','), is an illegal char here.")
        raise SyntaxError("Do not use commas (',')")


# noinspection PyShadowingNames
def check_opt(opt_input: str, escape: bool = False, fast_mode: bool = False,
              both_modes: bool = False) -> bool:
    """Function that checks the integrity of the listen option. Options codes
    of the interactive and the fast mode can be passed.

    escape flag set to true is to indicate that the check is only to validate
    if opt is a correct escape command, discarding the other option commands.
    Use the others flags expands this case.

    The fast mode options should to be passed with the fast_mode bool flag
    set to true. This is because there are some options that only works for one
    of the modes.

    The both_mode flag may be passed to true to check if one option is valid
    for at least one of the two program modes.

    If both_modes is passed set to true, the result will include fast_mode
    necessary. So both_modes set to true overwrite fast_mode and always set
    it to true. And evidently, also includes escape commands.

    Note that the default mode, if all flags are passed set to false or are
    not passed is the for interactive mode options check.

    :param opt_input: User input option
    :type opt_input: str
    :param escape: Flag to indicate that the check is only to validate if opt
        is a correct escape command
    :type escape: bool
    :param fast_mode: Flag to indicate that the option provides to a fast mode
        call
    :type fast_mode: bool
    :param both_modes: Flag to check if the passed opt its valid for at least
        one of the modes: "opt is ok for interactive or fast mode?"
    :type both_modes: bool
    :return: Confirmation about the validation of the passed option
    :rtype: bool
    """
    # Always included options stock
    opts_stock = dictionary.cmds_escape

    if not escape:
        if both_modes:  # Full extension
            opts_stock.extend(dictionary.get_union_cmds_set())
        else:
            if not fast_mode:  # Interactive mode extension
                opts_stock.extend(dictionary.cmds_interactive_mode)
            else:  # Fast mode extension
                opts_stock.append(dictionary.cmds_fast_mode)

    if any(opt_input == opt_pattern for opt_pattern in opts_stock):
        return True
    else:
        return False


# noinspection PyShadowingNames
def check_profile(profname: str) -> bool:
    """Function that checks if a gitcher profile exists.

    :param profname: Name of the gitcher profile to operate with
    :type profname: str
    :return: Confirmation about the existence of gitcher profile required
    :rtype: bool
    """
    try:
        recover_prof(profname)
        return True
    except NotFoundProfError:
        return False  # If not finds prof


# noinspection PyShadowingNames
def recover_prof(profname: str) -> Prof:
    """Function that recovers a gitcher profile through a model query.

    Warnings:
        - CHERFILE can not content two profiles with the same name. The add
            function takes care of it.

    :param profname: Name of the gitcher profile to operate with
    :type profname: str
    :return: gitcher profile required
    :rtype: Prof
    :raise: NotFoundProfError
    """
    try:
        return model_layer.model_recuperate_prof(profname)
    except NotFoundProfError:
        raise NotFoundProfError


# ===============================================
# =                Main launchers               =
# ===============================================

def print_current_on_prof() -> None:
    """Function that prints the current in use ON profile information.

    :return: None, print function
    """
    cprof = model_layer.model_recuperate_git_current_prof()  # Current profile

    # Now, cprof is compared against saved profiles list. cprof is an
    # extract of the git user configuration, that is independent of the
    # gitcher data and scope. So, with next operations it is checked if
    # current config is saved on gitcher, and it is created a mixed dataset to
    # print the information
    profs = model_layer.model_recuperate_profs()
    for prof in profs:
        if cprof.equivalent(prof):
            print(MSG_OK + " " + prof.profname + ": " + cprof.simple_str())
            return
    # If not found in list...
    print(MSG_OK + " Unsaved profile: " + cprof.simple_str())


# noinspection PyShadowingNames
def set_prof(profname: str) -> None:
    """Function that sets the selected profile locally.

    It is imperative that it be called from a directory with a git
    repository. Profile name must be checked before.

    :param profname: Name of the gitcher profile to operate with
    :type profname: str
    :return: None
    """
    if model_layer.check_git_context():
        model_layer.model_switch_prof(profname)
        print(MSG_OK + " Switched to {0} profile.".format(profname))
    else:
        print(MSG_ERROR + " Current directory not contains a git repository.")


# noinspection PyShadowingNames
def set_prof_global(profname: str) -> None:
    """Function that sets the selected profile globally.

    It is not necessary to be called from a directory with a git repository.
    Profile name must be checked before.

    :param profname: Name of the gitcher profile to operate with
    :type profname: str
    :return: None
    """
    model_layer.model_switch_prof(profname, '--global')
    print(MSG_OK + " Set {0} as git default profile.".format(profname))


# noinspection PyShadowingNames
def add_prof() -> None:
    """Function that adds a new profile on interactive mode. Profile name
    have not to be checked before.

    :return: None
    """
    print("\nLets go to add a new gitcher profile...")

    profname = listen("Enter the profile name: ")
    while check_profile(profname):
        print(MSG_ERROR + " {0} yet exists. Change name...".format(profname))
        profname = listen("Enter profile name: ")

    name = listen("Enter the git user name: ")

    email = listen("Enter the git user email: ")
    while not validate_email(email):
        print(MSG_ERROR + " Invalid email format. Try again...".format(email))
        email = listen("Enter the git user email: ")

    if yes_or_no("Do you want to use a GPG sign key?"):
        signkey = listen("Enter the git user signkey: ")
        signpref = yes_or_no("Do you want to autosign every commit?")
    else:
        signkey = None
        signpref = False

    # Save it...
    prof = model_layer.Prof(profname, name, email, signkey, signpref)
    model_layer.model_save_profile(prof)
    print(MSG_OK + " New profile {0} added.".format(profname))


# noinspection PyShadowingNames
def add_prof_fast(profname: str, name: str, email: str, signkey: str,
                  signpref: bool) -> None:
    """Function that adds a new profile on fast mode. Profile name have not
    to be checked before.

    :param profname:
    :type profname: str
    :param name:
    :type name: str
    :param email:
    :type email: str
    :param signkey:
    :type signkey: str
    :param signpref:
    :type signpref: bool
    :return: None
    """
    if not check_profile(profname):  # Profname have to be unique
        prof = model_layer.Prof(profname, name, email, signkey, signpref)
        model_layer.model_save_profile(prof)
        print(MSG_OK + " New profile {0} added.".format(profname))
    else:
        print(MSG_ERROR + " {0} yet exists!".format(profname))
        sys.exit("gitcher profile name already in use")


# noinspection PyShadowingNames
def update_prof() -> None:
    """Function that updates a profile on interactive mode. Profile name
    have not to be checked before.

    :return: None
    """
    print("\nLets go to update a gitcher profile...")

    old_profname = listen("Enter the profile name: ",
                          dictionary.profs_profnames)
    while not check_profile(old_profname):
        print(MSG_ERROR + " {0} not exists. Change name...".format(
            old_profname))
        old_profname = listen("Enter profile name: ",
                              dictionary.profs_profnames)

    prof = model_layer.model_recuperate_prof(old_profname)

    profname = old_profname
    if yes_or_no("Do you want to update the profile name?"):
        profname = listen("Enter the new profile name: ")
    name = prof.name
    if yes_or_no("Do you want to update the user name?"):
        name = listen("Enter the new name: ")
    email = prof.email
    if yes_or_no("Do you want to update the user email?"):
        email = listen("Enter the new email: ")
        while not validate_email(email):
            print(MSG_ERROR + " Invalid email format. Try again...".format(
                email))
            email = listen("Enter the new email: ")
    if yes_or_no("Do you want to update the GPG sign config?"):
        if yes_or_no("Do you want to use a GPG sign key?"):
            signkey = listen("Enter the git user signkey: ")
            signpref = yes_or_no("Do you want to autosign every commit?")
        else:
            signkey = None
            signpref = False
    else:
        signkey = prof.signkey
        signpref = prof.signpref

    # Remove the old profile
    model_layer.model_delete_profile(old_profname)
    # And save the new...
    prof = model_layer.Prof(profname, name, email, signkey, signpref)
    model_layer.model_save_profile(prof)
    print(MSG_OK + " Profile {0} updated.".format(profname))


# noinspection PyShadowingNames
def mirror_prof(origin_profname: str) -> None:
    """Function that mirrors a profile to create a duplicate of it.

    Profile name must be checked before.

    :param origin_profname: Name of the gitcher profile to operate with
    :type origin_profname: [str]
    :return: None
    """
    new_profname = listen("Enter the new profile name (can not be the same "
                          "that the origin profile): ")
    while check_profile(new_profname):
        print(MSG_ERROR + " {0} yet exists. Change name...".format(
            new_profname))
        new_profname = listen("Enter profile name: ")

    prof = model_layer.model_recuperate_prof(origin_profname)

    profname = new_profname
    name = prof.name
    email = prof.email
    signkey = prof.signkey
    signpref = prof.signpref

    # Save the new profile...
    prof = model_layer.Prof(profname, name, email, signkey, signpref)
    model_layer.model_save_profile(prof)
    print(MSG_OK + " Profile {0} created.".format(profname))


# noinspection PyShadowingNames
def delete_prof(profname: str) -> None:
    """Function that deletes the selected profile.

    Profile name must be checked before.

    :param profname: Name of the gitcher profile to operate with
    :type profname: [str]
    :return: None
    """
    model_layer.model_delete_profile(profname)
    print(MSG_OK + " Profile {0} deleted.".format(profname))


# ===============================================
# =                     MAIN                    =
# ===============================================

def interactive_main() -> None:
    """Main launcher of gitcher program interactive mode. Dialogue with the
    user.

    :return: None
    """
    print(COLOR_BRI_BLUE + "**** gitcher: the git profile switcher ****" +
          COLOR_RST)

    print("gitcher profiles list:")
    print_prof_list()
    print("\nOptions:")
    print(COLOR_BRI_CYAN + "s" + COLOR_RST + "    set a profile to current "
                                             "directory repository.")
    print(COLOR_BRI_CYAN + "g" + COLOR_RST + "    set a profile as global "
                                             "git configuration.")
    print(COLOR_BRI_CYAN + "a" + COLOR_RST + "    add a new profile.")
    print(COLOR_BRI_CYAN + "u" + COLOR_RST + "    update a profile.")
    print(COLOR_BRI_CYAN + "m" + COLOR_RST + "    mirror a profile to create a"
                                             " duplicate.")
    print(COLOR_BRI_CYAN + "d" + COLOR_RST + "    delete a profile.")
    print("\nInput " + COLOR_BRI_CYAN + "quit" + COLOR_RST + " or " +
          COLOR_BRI_CYAN + "exit" + COLOR_RST + "everywhere to quit.\n")

    opt = listen("Option: ", dictionary.get_union_cmds_set())
    while not check_opt(opt):
        print(MSG_ERROR + " Invalid opt! Use " +
              '|'.join(dictionary.cmds_interactive_mode) +
              ". Type exit to quit.")
        opt = listen("Enter option: ", dictionary.get_union_cmds_set())

    if not opt == 'a' and not opt == 'u':
        profname = listen("Select the desired profile entering its name: ",
                          dictionary.profs_profnames)
        while not check_profile(profname):
            print_prof_error(profname)
            profname = listen("Enter profile name: ",
                              dictionary.profs_profnames)

        if opt == 's':
            set_prof(profname)
        elif opt == 'g':
            set_prof_global(profname)
        elif opt == 'm':
            mirror_prof(profname)
        else:  # Option 'd'
            if yes_or_no(MSG_WARNING + " Are you sure to delete {0}?".format(
                    profname)):
                delete_prof(profname)
    else:
        if opt == 'a':
            add_prof()
        else:  # Option 'u'
            update_prof()


def fast_main(cmd: [str]) -> None:
    """Runs fast passed options after to do necessary checks.

    :param cmd: Command line order by the user
    :type cmd: [str]
    :return: None
    """
    # First, check param syntax
    for param in cmd:
        try:
            check_syntax(param)
        except SyntaxError:
            sys.exit("Syntax error")

    # If syntax is ok, go on and check selected option
    opt = cmd[1].replace('-', '')
    if not check_opt(opt, fast_mode=True):
        print(MSG_ERROR + " Invalid option! Use -" +
              '-|'.join(dictionary.cmds_fast_mode))
        sys.exit("Invalid option")
    else:
        if opt == 'o':
            if len(cmd) == 2:  # cmd have to be only 'gitcher <-o>'
                print_current_on_prof()
            else:
                raise_order_format_error()
        elif len(cmd) >= 3:  # cmd have to be 'gitcher <-opt> <profname> [...]'
            # Catch profname, first parameter for all cases
            profname = cmd[2]

            if opt == 'a':
                if len(cmd) != 7:  # cmd have to be 'gitcher <-opt> <profname>
                    # <name> <email> <signkey> <signpref>'
                    raise_order_format_error()
                # Catch specific params
                name = cmd[3]
                email = cmd[4]
                if not validate_email(email):
                    raise_order_format_error(email)
                signkey = cmd[5]
                if signkey == 'None':
                    signkey = None
                signpref = cmd[6]
                if signpref == 'True':
                    signpref = True
                elif signpref == 'False':
                    signpref = False
                else:
                    raise_order_format_error(cmd[5])

                add_prof_fast(profname, name, email, signkey, signpref)
            else:  # Else it is always necessary to check the profile
                if len(cmd) == 3:  # Security check
                    if not check_profile(profname):
                        print_prof_error(profname)
                        sys.exit("gitcher profile not exists")
                    # Else, if the profile exists, continue...
                    if opt == 's':
                        set_prof(profname)
                    elif opt == 'g':
                        set_prof_global(profname)
                    elif opt == 'd':
                        delete_prof(profname)
                else:
                    raise_order_format_error()
        else:
            raise_order_format_error()


if __name__ == "__main__":
    # First, check if git is installed
    if not model_layer.check_git_installed():
        print(
            MSG_ERROR + " git is not installed in this machine. Impossible to "
                        "continue.")
        sys.exit("git is not installed")

    # Next, check if CHERFILE exists. If not and gitcher is ran as
    # interactive mode, propose to create it
    cherfile = model_layer.CHERFILE
    if not os.path.exists(cherfile):
        print(MSG_ERROR + " {0} not exists and it is necessary.".format(
            cherfile))

        if (len(sys.argv)) > 1:
            if yes_or_no("Do you want to create {0}?".format(cherfile)):
                open(cherfile, 'w')
                print(MSG_OK + " Gitcher config dotfile created. Go on...")
            else:
                print(MSG_ERROR + "Impossible to go on without gitcher "
                                  "dotfile.")
                sys.exit("No gitcher file")
        else:
            sys.exit("No gitcher file")

    # Now, create an unique instance for the execution gitcher dictionary
    dictionary = dictionary.Dictionary()

    # After firsts checks, run gitcher
    if (len(sys.argv)) == 1:  # Interactive mode
        interactive_main()
    elif (len(sys.argv)) > 1:  # Fast mode
        fast_main(sys.argv)
