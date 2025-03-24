#!/usr/local/bin/python3
import gnupg
import sys
import os.path
import glob
import argparse
import json
import textwrap
from collections import OrderedDict

BINARY = '/usr/local/bin/gpg'
GPG_DIR = '~/.gnupg/'
FILE = 'secrets'
KEYS = OrderedDict([('user', None), ('password', None), ('url', None), ('other', None)])
gpg=gnupg.GPG(binary=BINARY,homedir=GPG_DIR)

def get_keys():
	files = glob.glob('./pub-keys/*.asc')
	keys_data = ''
	for name in files:
		try:
			with open(name) as file:
				 keys_data+=str(file.read())
		except IOError as exc:
			if exc.errno != errno.EISDIR: # Do not fail if a directory is found, just ignore it.
				raise # Propagate other kinds of IOError.
	import_result = gpg.import_keys(keys_data)
	fprints=[]
	for key in import_result.results:
		fprints.append(str(key['fingerprint']))
	return fprints

def encrypt_content(json_content):
	finger_prints = get_keys()
	return gpg.encrypt(json_content, *finger_prints, always_trust=True, output=FILE)

def decrypt_content():
	file = open(FILE, 'a+')
	file.seek(0)
	return gpg.decrypt(file.read())

def update_keys():
	encrypt_content(str(decrypt_content()))

def get_key_value(args, option):
	json_content = json.loads(str(decrypt_content()))
	if option.lower() == 'all':
		for e in KEYS:
			print(e.capitalize()+':',json_content[args][e])
	elif option.lower() == 'user': print(json_content[args]['user'])
	elif option.lower() == 'pass': print(json_content[args]['password'])
	elif option.lower() == 'url': print(json_content[args]['url'])
	elif option.lower() == 'other': print(json_content[args]['other'])

def id_or_list():
	json_content = json.loads(str(decrypt_content()))
	id = input("Introduce the identifier name or 'list' for list all identifiers: ").replace(' ','_')
	while id.lower()=='list' or id not in json_content:
		if id.lower()=='list' :
			show_keys()
			id = input("Introduce the identifier name or 'list' for list all identifiers: ").replace(' ','_')
		if id not in json_content:
			id = input("Introduce a valid identifier name or 'list' for list all identifiers: ").replace(' ','_')
	return id

def print_decrypt_content():
	id = id_or_list()
	json_content = json.loads(str(decrypt_content()))

	output = input('Show values? (Y/n): ' )
	while output.lower() != 'y' and output.lower() != 'n' and output.lower() != 'yes' and output.lower() != 'no' and output.lower() != '':
		output = input('Show values? (Y/n): ' )

	if output.lower() == '' or output.lower() == 'y' or output.lower() == 'yes':
		for e in KEYS:
			print(str(e) + ': ' + str(json_content[id][e]))

	output = input('Copy any elemento to clipboard? (N/element name): ' )
	while output not in KEYS and output.lower() != '' and output.lower() != 'n' and output.lower() != 'no':
		output = input('Please choose "no" for leave. For copy and element "user", "password", "url" or "other": ' )

	if output.lower() != '' and  output.lower() != 'no' and output.lower() != 'n':
		os.system("echo '{}' | pbcopy".format(json_content[id][output.lower()]))

def modify_content():
	id = id_or_list()
	json_content = json.loads(str(decrypt_content()))
	json_content.pop(id, None)
	new_json = {}
	print("Leave all elements without value for delete the entry")

	for e in KEYS:
		element = input("New " + str(e) + ": ")
		new_json[e] = element

	if all( values == '' for key, values in new_json.items()):
		jkv = json.dumps(json_content, sort_keys=True)
		encrypt_content(jkv)
		print("Done! Identifier " + id +" has been deleted")
	else:
		json_content[id] = new_json
		jkv = json.dumps(json_content, sort_keys=True)
		encrypt_content(jkv)
		print("Done! Identifier " + id +" has been modified")

def show_keys():
	json_content = json.loads(str(decrypt_content()))
	for key in sorted(json_content.keys()):
		print(key)

def add_content(id, old_content = None):
	json_content = {}

	for el in KEYS:
		KEYS[el] = input('Please introduce a value for "' + str(el.lower()) + '" field, or leave it empty: ')

	if old_content:
		old_content[id] = KEYS
		json_content = old_content
	else:
		json_content[id] = KEYS

	jkv = json.dumps(json_content, sort_keys=True)
	encrypt_content(jkv)

def add_menu():
	file  = open('secrets', 'a+')
	json_content = json.loads(str(decrypt_content()))

	id = input('Please Introduce an Identifier: ').replace(' ','_')
	while (id in json_content):
		id = input('This identifier exist. Please Introduce other Identifier: ').replace(' ','_')
	json_content = add_content(id, json_content)

def initialize():
	id = input('Please Introduce an Identifier: ').replace(' ','_')
	add_content(id)

def input_menu(option, switcher):
	while True:
		try:
			option = int(option)
			if option not in range(1,switcher): raise ValueError
			break
		except:
			option = input('Please, choose correct option: ')
	return option

def interactive_menu():
	if os.path.isfile(FILE):
		switcher = {
			0: lambda: '',
        		1: add_menu,
        		2: modify_content,
        		3: print_decrypt_content,
        		4: show_keys,
        		5: update_keys,
        		6: exit
    		}
		option = input('\t1: Add Key/Value Pair\n\t2: Modify/Delete Key/Value Pair\n\t3: Decrypt Key/Value Pair\n\t4: Show Keys\n\t5: Update public keys\n\t6: Exit\nChoose: ')
		option = input_menu(option, len(switcher))
		func = switcher.get(option, lambda: 'nothing')
		return func()

	else:
		print('The file', FILE,'has not been found, using -i/--interactive argument.')
		switcher = {
			0: lambda: '',
        		1: initialize,
        		2: exit
    		}
		option = input('\t1: Add\n\t2: Exit\nChoose: ')
		option = input_menu(option, len(switcher))
		func = switcher.get(option, lambda: 'nothing')
		return func()

def exit():
	sys.exit(0)

def main(argv):
	parser = argparse.ArgumentParser(description='Manager for sensible information under PGP')
	parser.add_argument("-i","--interactive", help="display the interactive menu for pwd-manager",
		action="store_true")
	parser.add_argument("-l","--list", help="list all the stored identifiers", action="store_true")
	parser.add_argument("-u","--user", metavar='identifier', help="return the username for the given identifier")
	parser.add_argument("-p","--password", metavar='identifier', help="return the password for the given identifier")
	parser.add_argument("-ur","--url", metavar='identifier', help="return the URL for the given identifier")
	parser.add_argument("-o","--other", metavar='identifier', help="return the other for the given identifier")
	parser.add_argument("-a","--all", metavar='identifier', help="display all values for the given identifier")
	args = parser.parse_args()
	if args.interactive: interactive_menu()
	elif args.list: show_keys()
	elif args.user: get_key_value(args.user, 'user')
	elif args.password: get_key_value(args.password, 'pass')
	elif args.url: get_key_value(args.url, 'url')
	elif args.other: get_key_value(args.other, 'other')
	elif args.all: get_key_value(args.all, 'all')
	elif not os.path.isfile(FILE): interactive_menu()
	else: parser.print_help()

if __name__ == "__main__":
	main(sys.argv[1:])
