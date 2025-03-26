import hashlib
import itertools
import string
import argparse
import subprocess
import sys
 
assert string.ascii_lowercase == 'abcdefghijklmnopqrstuvwxyz'
 
def brute_force_md5(target_hash, minimum_char=1, log=True, skip_id=0, skip_count=1):
    for i in range(minimum_char, 6):
        product = itertools.product(string.ascii_lowercase + string.digits, repeat=i)
        char_space = itertools.imap(''.join, product)
        if log:
            print
            print "Worker %d: Beginning strings of length %d..." % (skip_id, i)
 
        for iteration_num, combination in enumerate(char_space):
            if iteration_num % skip_count != skip_id:
                continue
            if hashlib.md5(combination).hexdigest() == target_hash:
                if log:
                    print "Worker %d: Found hash at %s" % (skip_id, combination)
                return combination
 
        if log:
            print "Worker %d: ...And searched. No result found." % skip_id
 
def test_brute_force_md5():
    thehash = hashlib.md5("ab").hexdigest()
    assert brute_force_md5(thehash) == "ab"
 
parser = argparse.ArgumentParser()
parser.add_argument("-w", "--worker", default=0, type=int)
parser.add_argument("-x", "--workers", default=1, type=int)
parser.add_argument("-p", "--parallelize", default=None, type=int)
parser.add_argument("target_hash")
 
def parallelize(target_hash, worker_count):
    workers = []
    for worker_id in range(worker_count):
        proc = subprocess.Popen([
            sys.executable, __file__, 
            "--worker", str(worker_id),
            "--workers", str(worker_count),
            target_hash])
        workers.append(proc)
    for proc in workers:
        proc.wait()
 
def main():
    args = parser.parse_args()
    if args.parallelize is not None:
        parallelize(args.target_hash, args.parallelize)
    else:
        print brute_force_md5(args.target_hash, skip_count=args.workers, skip_id=args.worker)
 
if __name__ == "__main__":
    main()
