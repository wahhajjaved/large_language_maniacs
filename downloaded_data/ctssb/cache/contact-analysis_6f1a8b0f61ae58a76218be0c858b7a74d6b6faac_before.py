from dictionary import Dictionary
from loader import file_to_dict
from score import score, highest_score
from pprint import pprint
import sys

def main():
    try:
        arg1 = sys.argv[1]
    except:
        arg1 = 'help'

    if arg1 == 'help':
        contact_help()
    else:
        try:
            arg2 = sys.argv[2]
        except:
            print "You must provide a valid argument. See help for details"
            return
        if arg2 not in 'print' and \
                arg2 not in 'scores' and \
                arg2 not in 'highest':
            print "You must provide an argument. See help for details"
            return            
        dic = file_to_dict(arg1)
        if arg2 == 'print':
            dic.print_dict()
        elif arg2 == 'scores':
            pprint(score(dic))
        elif arg2 == 'highest':
            word = highest_score(dic)
            print "The highest scoring word is..."
            print word['word'], word['score']
        else:
            print "See help for options"

def contact_help():
    print "\n#################################\n"
    print "HELP CALLED FOR!"
    print "python contact-analysis <dictionary> <option>"
    print "\t<option> - 'score' or 'highest' or 'print'\n"
    return

if __name__ == "__main__":
    main()
