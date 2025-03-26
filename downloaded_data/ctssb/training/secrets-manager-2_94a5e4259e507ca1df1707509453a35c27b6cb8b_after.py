import pytest
import builtins
import os
import json
import pyperclip
import platform
import time
from interactive_cmd import InteractiveCMD
from gpg_tools import GPGTools

if os.path.isfile('secrets'):
	timestr = time.strftime("%Y%m%d-%H%M%S")
	os.rename('secrets', '._secrets.bkp'+str(timestr))

for i in range(1,100):
	if os.path.isfile('secrets'+str(i)): os.remove('secrets'+str(i))

def get_files(file_name1, file_name2):
	file1 = open(file_name1, 'w')
	file1.write("-----BEGIN PGP MESSAGE-----\n\nhQIMA+HIES/TSZytAQ//XFNQVedjCG5VLoyhbnOQjhAfVvuBxnZp0kfkPj3iGH+a\nefC2pZ/uzwYEkZgZa8JoOT4MIguex5UEy8YehsDZ3omGnkK4lSyYXy1BTG4LxQBG\nmRMmufVZJtU4W0q8Syce7cfA6FXR7AdECCegmkdJ/5nngJvEoLEB7MXFT7idGf5+\n2fAYfJJ/C6p6Y54xnFmh1NIAYZuYfw/MQaT2q5nJUn0y+FfxE2Zapj4Vr0mU4bsY\np/Wj5axEo0GVSiFHZL3ToYhOi7eRFqIvfJ/Wid8MIuuw79KnuRjVPzBnWKhMbF4z\nFxvjaKcpRPjNsZDgXCx9rkwFEwkYG1KqmWionZO0uj9Iut1S6+SEf/6r41Q2hjwn\nXUNA8oq45MXRC8X2vhOfWUJcdjj7JEf/K0TkIkSJhQn/vIUOShcNgTNKdDbVCJkE\n5oxdSkSOizGXN44wKLPaCccKyH02eJiO+LXvkRWcIP9kRrtAC5WnDAtod0N+NgSw\nGOnDqQxuQwJ6J7AOIz29lwxF27aXis5sxTz2UK4f9Fw1FvTp1YD32zDBS2w82BWy\nyZmIcp2VaR4hWrTC5atTel17co/gVfquaeyDWs3zQ9u116hRRctUS+m4o4l8HGdS\nZq4nB/pBlXQYFGLaeGaZB1pcUm1/Yq17lLzTZ01/OXwCma61cqIEY9Q6WuKZ0nyF\nAgwDCDQBmit7oo4BD/sEdmO9bU0k2AX3PrDeA2FkkTVgcctpzFvYDSOCKPs5fmL+\n3rSsYKcudSoiC4qcPiYaPave+h4UDnGq7MShW8dkQeZUFJpeZdf/UMjrnoeSdMgg\nPoWIJtD/tbobqtnVBXY/cvoQYaIQLpC2PEvOwDooxYb69fSyujKXkngR0MXt1Q9V\nyGOdDBRN5SGlEDcIWE1kz8J9dDgVt0D27uqOTdFKBSpA11/3SFCyvdQkIisuQK8v\nLJydAmD1XpewMPnbTvcE+zClUFjLRgdI1sYgHCE5ubHKB04wGQhtrNj8c5V/IyGg\ndRQsfnD7WflSpCjQUfUxCi+fDQg3ZgPiJgi4ao75LskNIovdkiZVaeI4Y0LCCIqI\nSLM0kfOKDJtV28yZgGPRCSuHT7lwi9x74ULj3/P6sWgerxrsZOY4KDlcgzVirYdc\nYgvYi4kEMgS4vJ5PGAQlYD37RZ+McDnCEzSdNQd0aIOGGVYhyBaVbGJgpDxJX5bJ\nrGO2E7NWsF77qNxto+e63IeKAO1pSS/a7r+lqfcGazcp3ZoaNHYdU5psJgf27siI\nxWZhrSMno3e/yYUHO+I6IX8Oswf4mH2pUWrong5MziLd9EPvSD5ijZe84dREUlzz\nmxJd+7eFFPDLA39hgsgdKjL5mrPEbV++GbVg3AokFhQrQlfeZmyGu1kI9/c/mtJx\nAZ/D+V9CJV7IEOWqDSw8OTh2GH0gAHqcalJnnA3Y37LJ15v+BiT88JZfj6VJReFN\nWJZvKBqSj8+DaHZfQxkigALejbIvCAFmZr3iVgmZYpuTmE4Rumwa07x2+JlhJkti\nCCpzx4qpAAdMhKRp+X4WbEI=\n=zd48\n-----END PGP MESSAGE-----")
	file1.close()

	file2 = open(file_name2, 'w')
	file2.write("-----BEGIN PGP MESSAGE-----\n\nhQIMA+HIES/TSZytAQ//XFNQVedjCG5VLoyhbnOQjhAfVvuBxnZp0kfkPj3iGH+a\nefC2pZ/uzwYEkZgZa8JoOT4MIguex5UEy8YehsDZ3omGnkK4lSyYXy1BTG4LxQBG\nmRMmufVZJtU4W0q8Syce7cfA6FXR7AdECCegmkdJ/5nngJvEoLEB7MXFT7idGf5+\n2fAYfJJ/C6p6Y54xnFmh1NIAYZuYfw/MQaT2q5nJUn0y+FfxE2Zapj4Vr0mU4bsY\np/Wj5axEo0GVSiFHZL3ToYhOi7eRFqIvfJ/Wid8MIuuw79KnuRjVPzBnWKhMbF4z\nFxvjaKcpRPjNsZDgXCx9rkwFEwkYG1KqmWionZO0uj9Iut1S6+SEf/6r41Q2hjwn\nXUNA8oq45MXRC8X2vhOfWUJcdjj7JEf/K0TkIkSJhQn/vIUOShcNgTNKdDbVCJkE\n5oxdSkSOizGXN44wKLPaCccKyH02eJiO+LXvkRWcIP9kRrtAC5WnDAtod0N+NgSw\nGOnDqQxuQwJ6J7AOIz29lwxF27aXis5sxTz2UK4f9Fw1FvTp1YD32zDBS2w82BWy\nyZmIcp2VaR4hWrTC5atTel17co/gVfquaeyDWs3zQ9u116hRRctUS+m4o4l8HGdS\nZq4nB/pBlXQYFGLaeGaZB1pcUm1/Yq17lLzTZ01/OXwCma61cqIEY9Q6WuKZ0nyF\nAgwDCDQBmit7oo4BD/sEdmO9bU0k2AX3PrDeA2FkkTVgcctpzFvYDSOCKPs5fmL+\n3rSsYKcudSoiC4qcPiYaPave+h4UDnGq7MShW8dkQeZUFJpeZdf/UMjrnoeSdMgg\nPoWIJtD/tbobqtnVBXY/cvoQYaIQLpC2PEvOwDooxYb69fSyujKXkngR0MXt1Q9V\nyGOdDBRN5SGlEDcIWE1kz8J9dDgVt0D27uqOTdFKBSpA11/3SFCyvdQkIisuQK8v\nLJydAmD1XpewMPnbTvcE+zClUFjLRgdI1sYgHCE5ubHKB04wGQhtrNj8c5V/IyGg\ndRQsfnD7WflSpCjQUfUxCi+fDQg3ZgPiJgi4ao75LskNIovdkiZVaeI4Y0LCCIqI\nSLM0kfOKDJtV28yZgGPRCSuHT7lwi9x74ULj3/P6sWgerxrsZOY4KDlcgzVirYdc\nYgvYi4kEMgS4vJ5PGAQlYD37RZ+McDnCEzSdNQd0aIOGGVYhyBaVbGJgpDxJX5bJ\nrGO2E7NWsF77qNxto+e63IeKAO1pSS/a7r+lqfcGazcp3ZoaNHYdU5psJgf27siI\nxWZhrSMno3e/yYUHO+I6IX8Oswf4mH2pUWrong5MziLd9EPvSD5ijZe84dREUlzz\nmxJd+7eFFPDLA39hgsgdKjL5mrPEbV++GbVg3AokFhQrQlfeZmyGu1kI9/c/mtJx\nAZ/D+V9CJV7IEOWqDSw8OTh2GH0gAHqcalJnnA3Y37LJ15v+BiT88JZfj6VJReFN\nWJZvKBqSj8+DaHZfQxkigALejbIvCAFmZr3iVgmZYpuTmE4Rumwa07x2+JlhJkti\nCCpzx4qpAAdMhKRp+X4WbEI=\n=zd48\n-----END PGP MESSAGE-----")
	file2.close()

def remove_files(list):
	for file in list:
		os.remove(str(os.getcwd()) + '/' + file)

def get_GPG(message, secrets_file, secrets_key):
	gpg = GPGTools(file = secrets_file, key = secrets_key)
	gpg.encrypt_content(message)

	return gpg

def test_id_or_list(monkeypatch, capsys):
	gpg = get_GPG('{"One": {"user":"user1","password":"pass1","url":"url1","other":"other1"}}',
					'secrets_tmp14', '12345')

	aux = ['list', 'One']
	def mock_input_user(*args, **kwargs):
		a = aux[0]
		del aux[0]
		return a

	monkeypatch.setattr(builtins, 'input',mock_input_user)

	icmd = InteractiveCMD(gpg)
	icmd.id_or_list()
	out, err = capsys.readouterr()

	assert out == 'One\n'

	remove_files(['secrets_tmp14'])

def test_add_content(monkeypatch):
	gpg = get_GPG('{"One": {"user":"user1","password":"pass1","url":"url1","other":"other1"},"Two": {"user":"user2","password":"pass2","url":"url2","other":"other2"}}',
					'secrets_tmp15', '12345')

	gpg2 = get_GPG('{"One": {"user":"user1","password":"pass1","url":"url1","other":"other1"}}',
					'secrets_tmp16', '12345')

	aux = ['Two', 'user2', 'pass2', 'url2', 'other2']
	def mock_input_user(*args, **kwargs):
		a = aux[0]
		del aux[0]
		return a

	monkeypatch.setattr(builtins, 'input',mock_input_user)

	icmd = InteractiveCMD(gpg2)
	icmd.add_content()

	json_gpg = json.loads(str(gpg.decrypt_content()))
	json_gpg2 = json.loads(str(gpg2.decrypt_content()))

	assert json_gpg == json_gpg2

	remove_files(['secrets_tmp15','secrets_tmp16'])

def test_add_content_no_secrets(monkeypatch):
	gpg = GPGTools(key = '12345')

	gpg2 = get_GPG('{"One": {"user":"user1","password":"pass1","url":"url1","other":"other1"}}',
					'secrets_tmp17', '12345')

	aux = ['One', 'user1', 'pass1', 'url1', 'other1']
	def mock_input_user(*args, **kwargs):
		a = aux[0]
		del aux[0]
		return a

	monkeypatch.setattr(builtins, 'input',mock_input_user)

	icmd = InteractiveCMD(gpg)
	icmd.add_content()

	json_gpg = json.loads(str(gpg.decrypt_content()))
	json_gpg2 = json.loads(str(gpg2.decrypt_content()))

	assert json_gpg == json_gpg2

	remove_files(['secrets','secrets_tmp17'])

def test_modify_content(monkeypatch, capsys):
	gpg = get_GPG('{"One": {"user":"user1","password":"pass1","url":"url1","other":"other1"}}',
					'secrets_tmp18', '12345')

	gpg2 = get_GPG('{"One": {"user":"user2","password":"pass1","url":"url1","other":"other1"}}',
					'secrets_tmp19', '12345')

	aux = ['One', 'user2', 'pass1', 'url1','other1']
	def mock_input_user(*args, **kwargs):
		a = aux[0]
		del aux[0]
		return a

	monkeypatch.setattr(builtins, 'input',mock_input_user)

	icmd = InteractiveCMD(gpg)
	icmd.modify_content()
	out, err = capsys.readouterr()

	json1 = json.loads(str(gpg.decrypt_content()))
	json2 = json.loads(str(gpg2.decrypt_content()))

	assert json1['One']['user'] == json2['One']['user']
	assert out == 'Leave all elements without value for delete the entry\nDone! Identifier One has been modified\n'

	remove_files(['secrets_tmp18','secrets_tmp19'])

def test_modify_content_delete(monkeypatch, capsys):
	gpg = get_GPG('{"One": {"user":"user1","password":"pass1","url":"url1","other":"other1"}}',
					'secrets_tmp20', '12345')

	aux = ['One', '', '', '','']
	def mock_input_user(*args, **kwargs):
		a = aux[0]
		del aux[0]
		return a

	monkeypatch.setattr(builtins, 'input',mock_input_user)

	icmd = InteractiveCMD(gpg)
	icmd.modify_content()
	out, err = capsys.readouterr()

	json1 = json.loads(str(gpg.decrypt_content()))

	assert json1 == {}
	assert out == 'Leave all elements without value for delete the entry\nDone! Identifier One has been deleted\n'

	remove_files(['secrets_tmp20'])

def test_show_keys(capsys):
	gpg = get_GPG('{"One": 1, "Two": 2}', 'secrets_tmp21', '12345')

	icmd = InteractiveCMD(gpg)
	icmd.show_keys()

	out, err = capsys.readouterr()

	assert out == 'One\nTwo\n'

	remove_files(['secrets_tmp21'])

def test_update_keys():
	get_files('secrets_tmp22', 'secrets_tmp23')

	gpg = GPGTools(file = 'secrets_tmp22', key = '12345')
	icmd = InteractiveCMD(gpg)
	icmd.update_keys()

	file1 = open('secrets_tmp22','r')
	file2 = open('secrets_tmp23','r')

	assert file1.read() != file2.read()

	remove_files(['secrets_tmp22','secrets_tmp23'])

def test_no_update_keys():
	''' This test ensure that the codification works properly
	in the future this could be moved to the test_gpg_tools
	'''
	get_files('secrets_tmp24', 'secrets_tmp25')

	gpg = GPGTools(file = 'secrets_tmp24', key = '12345')
	icmd = InteractiveCMD(gpg)

	file1 = open('secrets_tmp24','r')
	file2 = open('secrets_tmp25','r')

	assert file1.read() == file2.read()

	remove_files(['secrets_tmp24','secrets_tmp25'])

def test_decrypt_content_ok(monkeypatch, capsys):
	gpg = get_GPG('{"One": {"user":"user1","password":"pass1","url":"url1","other":"other1"}}',
					'secrets_tmp25', '12345')

	aux = ['One','Y','N']
	def mock_input_user(*args, **kwargs):
		a = aux[0]
		del aux[0]
		return a

	monkeypatch.setattr(builtins, 'input',mock_input_user)

	icmd = InteractiveCMD(gpg)
	icmd.print_decrypt_content()
	out, err = capsys.readouterr()

	assert out == 'user: user1\npassword: pass1\nurl: url1\nother: other1\n'

	remove_files(['secrets_tmp25'])

def test_decrypt_content_ko(monkeypatch, capsys):
	gpg = get_GPG('{"One": {"user":"user1","password":"pass1","url":"url1","other":"other1"}}',
					'secrets_tmp26', '12345')

	aux = ['One','Y','N']
	def mock_input_user(*args, **kwargs):
		a = aux[0]
		del aux[0]
		return a

	monkeypatch.setattr(builtins, 'input',mock_input_user)

	icmd = InteractiveCMD(gpg)
	icmd.print_decrypt_content()
	out, err = capsys.readouterr()

	assert out != 'user: user\npassword: pass1\nurl: url1\nother: other1\n'

	remove_files(['secrets_tmp26'])

def test_decrypt_content_fail_id(monkeypatch, capsys):
	gpg = get_GPG('{"One": {"user":"user1","password":"pass1","url":"url1","other":"other1"}}',
					'secrets_tmp27', '12345')

	aux = ['Two','One','Y','N']
	def mock_input_user(*args, **kwargs):
		a = aux[0]
		del aux[0]
		return a

	monkeypatch.setattr(builtins, 'input',mock_input_user)

	icmd = InteractiveCMD(gpg)
	icmd.print_decrypt_content()
	out, err = capsys.readouterr()

	assert out == 'user: user1\npassword: pass1\nurl: url1\nother: other1\n'

	remove_files(['secrets_tmp27'])

def test_decrypt_content_copy_clipboard(monkeypatch, capsys):
	gpg = get_GPG('{"One": {"user":"user1","password":"pass1","url":"url1","other":"other1"}}',
					'secrets_tmp28', '12345')

	aux = ['One','N','password']
	def mock_input_user(*args, **kwargs):
		a = aux[0]
		del aux[0]
		return a

	monkeypatch.setattr(builtins, 'input',mock_input_user)

	icmd = InteractiveCMD(gpg)
	icmd.print_decrypt_content()

	if platform.system() == 'Darwin':
		clip_out = pyperclip.paste()
		assert clip_out == 'pass1'
	else:
		out, err = capsys.readouterr()
		assert out == ''

	remove_files(['secrets_tmp28'])

def test_exit():
	gpg = GPGTools()

	icmd = InteractiveCMD(gpg)
	with pytest.raises(SystemExit):
		icmd.exit()
