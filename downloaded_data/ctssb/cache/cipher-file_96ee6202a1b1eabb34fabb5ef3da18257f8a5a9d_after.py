#!/usr/bin/env python
####
# Cypher-file: contains functions to encipher and decipher files into base64 with a key.
# written by Brewster Mitchell
#   April 11, 2016
# See LICENSE.md for license terms.
#
# Usage == arguments: [e/d] [file in] [file out] [key(password)]
#
#####

import sys
import base64
from Crypto.Cipher import XOR

# params for running as main
enc_or_dec = sys.argv[1]
in_f = sys.argv[2]
out_f = sys.argv[3]
key_in = sys.argv[4]


## plain base64 deprecated

def encrypt_64(in_file, out_file):
  with open(in_file, 'rb') as f:
    encoded = base64.b64encode(f.read())
    with open(out_file, 'wb') as w:
      w.write(encoded)


def decrypt_64(in_file, out_file):
  with open(in_file, 'rb') as f:
    decoded = base64.b64decode(f.read())
    with open(out_file, 'wb') as w:
      w.write(decoded)


## function calls
# encrypt_64(in_f, out_f)
# decrypt_64(out_f, 'result.xml')

# XOR + b64

def encrypt_XOR(key, plaintext):
  cipher = XOR.new(key)
  return base64.b64encode(cipher.encrypt(plaintext))


def decrypt_XOR(key, ciphertext):
  cipher = XOR.new(key)
  return cipher.decrypt(base64.b64decode(ciphertext))


def encfile_XOR(in_file, out_file, key):
  with open(in_file) as f:
    encoded = encrypt_XOR(key, f.read())
    print(in_file + ' encrypted as ' + out_file)
    with open(out_file, 'w') as w:
      w.write(encoded.decode("utf-8"))


def decfile_XOR(in_file, out_file, key): ## CAUTION: decrypting with invalid key will produce invalid results rather than error!!!
  with open(in_file) as f:
    decoded = decrypt_XOR(key, f.read())
    print(in_file + ' decrypted as ' + out_file)
    with open(out_file, 'w') as w:
      w.write(decoded.decode("utf-8"))

def main():
  if enc_or_dec == 'e':
    encfile_XOR(in_f, out_f, key_in)
  elif enc_or_dec == 'd':
    decfile_XOR(in_f, out_f, key_in)
  else:
    print('invalid parameter at position 1. Expecting "e" or "d".')
  return

if __name__ == "__main__":
  main()