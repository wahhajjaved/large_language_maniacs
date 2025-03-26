import sys
import traceback

import theme_10.task_02.oops as oops


def safe(func, *args):
    try:
        func(*args)
    except:
        traceback.print_exc()
        print(sys.exc_info()[:2])


def main():
    for args in (oops.oops_indexerror, oops.oops_oopserror, 'spam'):
        safe(oops.main, args)


if __name__ == '__main__':
    main()
