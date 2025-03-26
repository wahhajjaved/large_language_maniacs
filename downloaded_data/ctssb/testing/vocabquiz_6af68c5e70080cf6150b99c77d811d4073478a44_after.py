import pandas as pd
import os
import random

def print_header():
    print("########################")
    print("##  Vocab quiz v0.1   ##")
    print("##  Niels Cautaerts   ##")
    print("########################")


def print_instructions():
    print("[i] import a selected vocab file")
    print("[t] get tested")
    print("[l] list the categories in the vocab list")
    print("[s] set test settings")
    print("[h] see these instructions")
    print("[p] print the wordlist for the current settings")
    print("[q] quit")


def get_vocablist(list_file = None):
    if list_file is None:
        #search all csv, xls and xlsx files in the directory
        allfiles = os.listdir() #standard is current directory
        allvoc = [filename for filename in allfiles if filename.endswith(".csv") or filename.endswith(".xls") or filename.endswith(".xlsx")]
        list_file = allvoc[0]

    if list_file.endswith(".xls") or list_file.endswith(".xlsx"):
        vocab_list = pd.read_excel(list_file)
    else:
        vocab_list = pd.read_csv(list_file)

    print("Imported {}".format(list_file))
    return vocab_list


def get_new_vocablist():
    list_file = input("Enter path to file: ")
    try:
        vocab_list = get_vocablist(list_file = list_file)
        return vocab_list
    except:
        print("Invalid filename or file not found.")
        return None


def vocab_loop(vcl = None, settings = ["m", ""]):
    if vcl is None:
        print("No valid vocab list")
    else:
        print("Press enter to continue, write :q to exit")
        word_list = vcl
        if settings[1]: #if the category is not empty, otherwise false and it doesn't go into this
            word_list = vcl[vcl.iloc[:,2]==settings[1]] #limit the words
        while True:
            #if the settings[0] are lr (left to right)
            fc = 0 #first column
            sc = 1 #second column
            #if the settings[1] are rl (right to left)
            if settings[0] == "rl":
                fc = 1
                sc = 0
            if settings[0] == "m": #random or mixed
                fc = random.choice([0,1])
                sc = 1-fc

            row = random.randint(0, len(word_list)-1) #randint is inclusive
            word = word_list.iloc[row, fc]
            translation = word_list.iloc[row, sc]
            langfc = word_list.columns[fc]
            langsc = word_list.columns[sc]

            inp = input("What is '{}' ({}) > ".format(word, langfc)).strip().lower()
            print("Answer: {} ({})".format(translation, langsc))
            if inp == ":q":
                break


def change_settings(vcl = None):
    if not vcl is None:
        print("To indicate what type of test you want, enter a command as:")
        print("[lr, rl, m] [cat] (e.g. 1 verbs)")
        print("lr means you are tested from left to right")
        print("rl means you are tested from right to left")
        print("m means you are tested both ways")
        print("the category name is optional if you want to limit the test to one")
        instruction = input("> ").strip().split()
        cats = get_categories(vcl)
        if len(instruction)==2:
            if instruction[0] in ["lr", "rl", "m"] and instruction[1] in cats:
                print("Settings updated to {}".format(instruction))
                return instruction
            else:
                print("Invalid settings")
                return None
        elif len(instruction)==1:
            if instruction[0] in ["lr", "rl", "m"]:
                print("Settings updated to [{} , '']".format(instruction[0]))
                return [instruction[0], ""]
            else:
                print("Invalid settings")
                return None
    else:
        print("No valid vocab list")


def get_categories(vcl):
    return list(vcl.iloc[:,2].unique())


def print_wordlist(vcl = None, settings = ["m", ""]):
    if vcl is None:
        print("No valid vocab list")
    else:
        word_list = vcl
        if settings[1]: #if the category is not empty, otherwise false and it doesn't go into this
            word_list = vcl[vcl.iloc[:,2]==settings[1]]
        print("Word list for settings: {}".format(settings))
        with pd.option_context('display.max_rows', None, 'display.max_columns', None):  # more options can be specified also
            print(word_list)


def print_categories(vcl = None):
    if not vcl is None:
        print(get_categories(vcl))
    else:
        print("No valid vocab list")

def main_loop():
    print_header()
    vcl = get_vocablist()
    print_instructions()
    settings = ["m", ""] #standard test settings: random way and no category
    while True:

        instruction = input("> ").lower().strip()
        if instruction == "i":
            vclt = get_new_vocablist()
            if not vclt is None:
                vcl = vclt

        elif instruction == "h":
            print_instructions()

        elif instruction == "q":
            print("Bye!")
            break

        elif instruction == "s":
            temp_settings = change_settings(vcl = vcl)
            if not temp_settings is None:
                settings = temp_settings

        elif instruction == "l":
            print_categories(vcl = vcl)

        elif instruction == "t":
            vocab_loop(vcl = vcl, settings = settings)

        elif instruction == "p":
            print_wordlist(vcl = vcl, settings = settings)

        else:
            print("Invalid instruction")


if __name__ == '__main__':
    main_loop()
