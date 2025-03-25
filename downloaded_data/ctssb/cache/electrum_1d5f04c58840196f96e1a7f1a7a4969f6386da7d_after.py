#!/usr/bin/env python
#
# Electrum - lightweight Bitcoin client
# Copyright (C) 2011 thomasv@gitorious
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

import sys
import datetime
import time
import copy
import argparse
import json

from util import print_msg, format_satoshis, print_stderr
from util import StoreDict
from bitcoin import is_valid, hash_160_to_bc_address, hash_160
from decimal import Decimal
import bitcoin
from transaction import Transaction


class Command:
    def __init__(self, name, requires_network, requires_wallet, requires_password, params, options, help, description):
        self.name = name
        self.requires_network = bool(requires_network)
        self.requires_wallet = bool(requires_wallet)
        self.requires_password = bool(requires_password)
        self.params = params
        self.options = options
        self.help = help
        self.description = description

known_commands = {}

def register_command(*args):
    global known_commands
    name = args[0]
    known_commands[name] = Command(*args)


#                command
#                                      requires_network
#                                        requires_wallet
#                                          requires_password
#                                               arguments
#                                                    options
register_command('listcontacts',       0, 0, 0, [], [], 'Show your list of contacts', '')
register_command('create',             0, 1, 0, [], [], 'Create a new wallet', '')
register_command('createmultisig',     0, 1, 0, [('num', 'number'), ('pubkeys', 'Public keys (json)')], [], 'Create multisig address', '')
register_command('createrawtx',        0, 1, 0, [('inputs', 'json'), ('outputs', 'json')], [], 'Create an unsigned transaction.', 'The syntax is similar to bitcoind.')
register_command('deseed',             0, 1, 0, [], [], 'Remove seed from wallet.', 'This creates a seedless, watching-only wallet.')
register_command('decoderawtx',        0, 0, 0, [('tx', 'Serialized transaction')], [], 'Decode raw transaction.', '')
register_command('getprivatekeys',     0, 1, 1, [('address', 'Bitcoin address')], [], 'Get the private keys of a wallet address.', '')
register_command('dumpprivkeys',       0, 1, 1, [], [], 'Dump private keys from your wallet', '')
register_command('freeze',             0, 1, 0, [('address', 'Bitcoin address')], [], 'Freeze address.', 'Freeze the funds at one of your wallet\'s addresses')
register_command('getbalance',         1, 1, 0, [], [], 'Return the balance of your wallet', '')
register_command('getservers',         1, 0, 0, [], [], 'Return the list of available servers', '')
register_command('getaddressbalance',  1, 0, 0, [('address', 'Bitcoin address')], [], 'Return the balance of an address', '')
register_command('getaddresshistory',  1, 0, 0, [('address', 'Bitcoin address')], [], 'Return the transaction history of a wallet address', '')
register_command('getconfig',          0, 0, 0, [('key', 'Variable name')], [], 'Return a configuration variable', '')
register_command('getpubkeys',         0, 1, 0, [('address', 'Bitcoin address')], [], 'Return the public keys for a wallet address', '')
register_command('gettransaction',     1, 0, 0, [('txid', 'Transaction ID')], ['deserialize'], 'Retrieve a transaction', '')
register_command('getseed',            0, 1, 1, [], [], 'Get seed phrase', 'Print the generation seed of your wallet.')
register_command('getmpk',             0, 1, 0, [], [], 'Get Master Public Key', 'Return your wallet\'s master public key')
register_command('help',               0, 0, 0, [], [], 'Print help on a command.', '')
register_command('history',            1, 1, 0, [], [], 'Wallet history', 'Returns the transaction history of your wallet')
register_command('importprivkey',      0, 1, 1, [('privkey', 'Private key')], [], 'Import a private key', '')
register_command('ismine',             0, 1, 0, [('address', 'Bitcoin address')], [], 'Check if address is in wallet', 'Return true if and only if address is in wallet')
register_command('listaddresses',      0, 1, 0, [], ['show_all', 'show_labels', 'frozen', 'unused', 'funded', 'show_balance'],
                 'List wallet addresses', 'Returns your list of addresses.')
register_command('listunspent',        1, 1, 0, [], [], 'List unspent outputs', 'Returns the list of unspent transaction outputs in your wallet.')
register_command('getaddressunspent',  1, 0, 0, [('address', 'Bitcoin address')], [], 'Returns the list of unspent inputs for an address.', '')
register_command('mktx',               0, 1, 1, [('recipient', 'Bitcoin address'), ('amount', 'Amount in BTC')],
                 ['tx_fee', 'from_addr', 'change_addr'], 'Create signed transaction', '')
register_command('payto',              1, 1, 1, [('recipient', 'Bitcoin address'), ('amount', 'Amount in BTC')],
                 ['tx_fee', 'from_addr', 'change_addr'], 'Create and broadcast a transaction.', '')
register_command('mktx_csv',           0, 1, 1, [('csv_file', 'CSV file of recipient, amount')], ['tx_fee', 'from_addr', 'change_addr'], 'Create a signed transaction', '')
register_command('payto_csv',          1, 1, 1, [('csv_file', '')], ['tx_fee', 'from_addr', 'change_addr'], 'Create and broadcast a transaction.', '')
register_command('password',           0, 1, 1, [], [], 'Change your password', '')
register_command('restore',            1, 1, 0, [], ['gap_limit', 'mpk', 'concealed'], 'Restore a wallet from seed', '')
register_command('searchcontacts',     0, 1, 0, [('query', '')], [], 'Search through contacts, return matching entries', '')
register_command('setconfig',          0, 0, 0, [('key', ''), ('value', '')], [], 'Set a configuration variable', '')
register_command('setlabel',           0, 1, 0, [('txid', 'Transaction ID'), ('label', '')], [], 'Assign a label to an item', '')
register_command('sendrawtx',          1, 0, 0, [('tx', 'Serialized transaction')], [], 'Broadcast a transaction to the network.', '')
register_command('signtxwithkey',      0, 0, 0, [('tx', 'raw_tx'), ('key', '')], [], 'Sign a serialized transaction with a key', '')
register_command('signtxwithwallet',   0, 1, 1, [('tx', 'raw_tx')], [], 'Sign a serialized transaction with a wallet', '')
register_command('signmessage',        0, 1, 1, [('address', 'Bitcoin address'), ('message', 'Message to sign.')], [],
                 'Sign a message with a key.', 'Use quotes if your message contains whitespaces')
register_command('unfreeze',           0, 1, 0, [('address', 'Bitcoin address')], [], 'Unfreeze the funds at one of your wallet\'s address', '')
register_command('validateaddress',    0, 0, 0, [('address', 'Bitcoin address')], [], 'Check that the address is valid', '')
register_command('verifymessage',      0, 0, 0, [('address', 'Bitcoin address'), ('signature', 'Signature'), ('message', 'Message')], [], 'Verify a signature', '')
register_command('version',            0, 0, 0, [], [], 'Return the version of your client', '')
register_command('encrypt',            0, 0, 0, [('pubkey', 'public key'), ('message', 'Message to encrypt.')], [],
                 'Encrypt a message with a public key.', 'Use quotes if the message contains whitespaces.')
register_command('decrypt',            0, 1, 1, [('pubkey', 'public key'), ('message', 'Encrypted message')], [], 'Decrypt a message encrypted with a public key', '')
register_command('getmerkle',          1, 0, 0, [('txid', 'Transaction ID'), ('height', 'Block height')], [], 'Get Merkle branch of a transaction included in a block', '')
register_command('getproof',           1, 0, 0, [('address', '')], [], 'Get Merkle branch of an address in the UTXO set', '')
register_command('getutxoaddress',     1, 0, 0, [('txid', 'Transction ID'), ('pos', 'Position')], [], 'Get the address of an unspent transaction output', '')
register_command('sweep',              1, 0, 0, [('privkey', 'Private key'), ('address', 'Destination address')], ['tx_fee'],
                 'Sweep private key.', 'Returns a transaction that sends all UTXOs to the destination address. The transactoin is not broadcasted.')
register_command('make_seed',          0, 0, 0, [], ['nbits', 'entropy', 'language'], 'Create a seed.', '')
register_command('check_seed',         0, 0, 0, [('seed', 'Seed phrase')], ['entropy', 'language'], 'Check that a seed was generated with external entropy.', '')



command_options = {
    'password':    ("-W", "--password",    None,  "Password"),
    'concealed':   ("-C", "--concealed",   False, "Don't echo seed to console when restoring"),
    'show_all':    ("-a", "--all",         False, "Include change addresses"),
    'frozen':      (None, "--frozen",      False, "Show only frozen addresses"),
    'unused':      (None, "--unused",      False, "Show only unused addresses"),
    'funded':      (None, "--funded",      False, "Show only funded addresses"),
    'show_balance':("-b", "--balance",     False, "Show the balances of listed addresses"),
    'show_labels': ("-l", "--labels",      False, "Show the labels of listed addresses"),
    'tx_fee':      ("-f", "--fee",         None,  "Transaction fee"),
    'from_addr':   ("-F", "--fromaddr",    None,  "Source address. If it isn't in the wallet, it will ask for the private key unless supplied in the format public_key:private_key. It's not saved in the wallet."),
    'change_addr': ("-c", "--changeaddr",  None,  "Change address. Default is a spare address, or the source address if it's not in the wallet"),
    'nbits':       (None, "--nbits",       128,   "Number of bits of entropy"),
    'entropy':     (None, "--entropy",     1,     "Custom entropy"),
    'language':    ("-L", "--lang",        None,  "Default language for wordlist"),
    'gap_limit':   ("-G", "--gap",         None,  "Gap limit"),
    'mpk':         (None, "--mpk",         None,  "Restore from master public key"),
    'deserialize': ("-d", "--deserialize", False, "Deserialize transaction"),
}


arg_types = {
    'num':int,
    'nbits':int,
    'entropy':long,
    'pubkeys':json.loads,
    'inputs': json.loads,
    'outputs':json.loads,
    'tx_fee':lambda x: (Decimal(x) if x is not None else None)
}


def set_default_subparser(self, name, args=None):
    """see http://stackoverflow.com/questions/5176691/argparse-how-to-specify-a-default-subcommand"""
    subparser_found = False
    for arg in sys.argv[1:]:
        if arg in ['-h', '--help']:  # global help if no subparser
            break
    else:
        for x in self._subparsers._actions:
            if not isinstance(x, argparse._SubParsersAction):
                continue
            for sp_name in x._name_parser_map.keys():
                if sp_name in sys.argv[1:]:
                    subparser_found = True
        if not subparser_found:
            # insert default in first position, this implies no
            # global options without a sub_parsers specified
            if args is None:
                sys.argv.insert(1, name)
            else:
                args.insert(0, name)

argparse.ArgumentParser.set_default_subparser = set_default_subparser

def add_network_options(parser):
    parser.add_argument("-1", "--oneserver", action="store_true", dest="oneserver", default=False, help="connect to one server only")
    parser.add_argument("-s", "--server", dest="server", default=None, help="set server host:port:protocol, where protocol is either t (tcp) or s (ssl)")
    parser.add_argument("-p", "--proxy", dest="proxy", default=None, help="set proxy [type:]host[:port], where type is socks4,socks5 or http")

def get_parser(run_gui, run_daemon, run_cmdline):
    # parent parser, because set_default_subparser removes global options
    parent_parser = argparse.ArgumentParser('parent', add_help=False)
    parent_parser.add_argument("-v", "--verbose", action="store_true", dest="verbose", default=False, help="Show debugging information")
    parent_parser.add_argument("-P", "--portable", action="store_true", dest="portable", default=False, help="Use local 'electrum_data' directory")
    # create main parser
    parser = argparse.ArgumentParser(
        parents=[parent_parser],
        epilog="Run 'electrum help <command>' to see the help for a command")
    subparsers = parser.add_subparsers(dest='cmd', metavar='<command>')
    # gui
    parser_gui = subparsers.add_parser('gui', parents=[parent_parser], description="Run Electrum's Graphical User Interface.", help="Run GUI (default)")
    parser_gui.add_argument("url", nargs='?', default=None, help="bitcoin URI (or bip70 file)")
    parser_gui.set_defaults(func=run_gui)
    parser_gui.add_argument("-g", "--gui", dest="gui", help="select graphical user interface", choices=['qt', 'lite', 'gtk', 'text', 'stdio'])
    parser_gui.add_argument("-m", action="store_true", dest="hide_gui", default=False, help="hide GUI on startup")
    parser_gui.add_argument("-L", "--lang", dest="language", default=None, help="default language used in GUI")
    parser_gui.add_argument("-o", "--offline", action="store_true", dest="offline", default=False, help="Run the GUI offline")
    parser_gui.add_argument("-w", "--wallet", dest="wallet_path", help="wallet path")
    add_network_options(parser_gui)
    # daemon
    parser_daemon = subparsers.add_parser('daemon', parents=[parent_parser], help="Run Daemon")
    parser_daemon.add_argument("subcommand", choices=['start', 'status', 'stop'])
    parser_daemon.set_defaults(func=run_daemon)
    add_network_options(parser_daemon)
    # commands
    for cmdname in sorted(known_commands.keys()):
        cmd = known_commands[cmdname]
        p = subparsers.add_parser(cmdname, parents=[parent_parser], help=cmd.help, description=cmd.help + ' ' + cmd.description)
        p.set_defaults(func=run_cmdline)
        if cmd.requires_password:
            p.add_argument("-W", "--password", dest="password", default=None, help="password")
        if cmd.requires_network:
            p.add_argument("-o", "--offline", action="store_true", dest="offline", default=False, help="Run command offline")
        if cmd.requires_wallet:
            p.add_argument("-w", "--wallet", dest="wallet_path", help="wallet path")
        for optname in cmd.options:
            a, b, default, help = command_options[optname]
            action = "store_true" if type(default) is bool else 'store'
            args = (a, b) if a else (b,)
            if action == 'store':
                _type = arg_types.get(optname, str)
                p.add_argument(*args, dest=optname, action=action, default=default, help=help, type=_type)
            else:
                p.add_argument(*args, dest=optname, action=action, default=default, help=help)

        for param, h in cmd.params:
            _type = arg_types.get(param, str)
            p.add_argument(param, help=h, type=_type)
    # 'gui' is the default command
    parser.set_default_subparser('gui')
    return parser



class Commands:

    def __init__(self, config, wallet, network, callback = None):
        self.config = config
        self.wallet = wallet
        self.network = network
        self._callback = callback
        self.password = None

    def _run(self, method, args, password_getter):
        cmd = known_commands[method]
        if cmd.requires_password and self.wallet.use_encryption:
            self.password = apply(password_getter,())
        f = getattr(self, method)
        result = f(*args)
        self.password = None
        if self._callback:
            apply(self._callback, ())
        return result

    def help(self):
        return 'Commands: ' + ', '.join(sorted(known_commands.keys()))

    def make_seed(self, nbits, custom_entropy, language):
        from mnemonic import Mnemonic
        s = Mnemonic(language).make_seed(nbits, custom_entropy=custom_entropy)
        return s.encode('utf8')

    def check_seed(self, seed, custom_entropy, language):
        from mnemonic import Mnemonic
        return Mnemonic(language).check_seed(seed, custom_entropy)

    def getaddresshistory(self, addr):
        return self.network.synchronous_get([ ('blockchain.address.get_history',[addr]) ])[0]

    def listunspent(self):
        l = copy.deepcopy(self.wallet.get_spendable_coins(exclude_frozen = False))
        for i in l: i["value"] = str(Decimal(i["value"])/100000000)
        return l

    def getaddressunspent(self, addr):
        return self.network.synchronous_get([('blockchain.address.listunspent',[addr])])[0]

    def getutxoaddress(self, txid, num):
        r = self.network.synchronous_get([ ('blockchain.utxo.get_address',[txid, num]) ])
        if r:
            return {'address':r[0]}

    def createrawtx(self, inputs, outputs):
        coins = self.wallet.get_spendable_coins(exclude_frozen = False)
        tx_inputs = []
        for i in inputs:
            prevout_hash = i['txid']
            prevout_n = i['vout']
            for c in coins:
                if c['prevout_hash'] == prevout_hash and c['prevout_n'] == prevout_n:
                    self.wallet.add_input_info(c)
                    tx_inputs.append(c)
                    break
            else:
                raise BaseException('Transaction output not in wallet', prevout_hash+":%d"%prevout_n)
        outputs = map(lambda x: ('address', x[0], int(1e8*x[1])), outputs.items())
        tx = Transaction.from_io(tx_inputs, outputs)
        return tx

    def signtxwithkey(self, raw_tx, sec):
        tx = Transaction(raw_tx)
        pubkey = bitcoin.public_key_from_private_key(sec)
        tx.sign({ pubkey:sec })
        return tx

    def signtxwithwallet(self, raw_tx):
        tx = Transaction(raw_tx)
        tx.deserialize()
        self.wallet.sign_transaction(tx, self.password)
        return tx

    def decoderawtransaction(self, raw):
        tx = Transaction(raw)
        return tx.deserialize()

    def sendrawtransaction(self, raw):
        tx = Transaction(raw)
        return self.network.synchronous_get([('blockchain.transaction.broadcast', [str(tx)])])[0]

    def createmultisig(self, num, pubkeys):
        assert isinstance(pubkeys, list), (type(num), type(pubkeys))
        redeem_script = Transaction.multisig_script(pubkeys, num)
        address = hash_160_to_bc_address(hash_160(redeem_script.decode('hex')), 5)
        return {'address':address, 'redeemScript':redeem_script}

    def freeze(self, addr):
        return self.wallet.set_frozen_state([addr], True)

    def unfreeze(self, addr):
        return self.wallet.set_frozen_state([addr], False)

    def getprivatekeys(self, addr):
        return self.wallet.get_private_key(addr, self.password)

    def ismine(self, addr):
        return self.wallet.is_mine(addr)

    def dumpprivkeys(self, addresses = None):
        if addresses is None:
            addresses = self.wallet.addresses(True)
        return [self.wallet.get_private_key(address, self.password) for address in addresses]

    def validateaddress(self, addr):
        isvalid = is_valid(addr)
        out = { 'isvalid':isvalid }
        if isvalid:
            out['address'] = addr
        return out

    def getpubkeys(self, addr):
        out = { 'address':addr }
        out['pubkeys'] = self.wallet.get_public_keys(addr)
        return out

    def getbalance(self, account= None):
        if account is None:
            c, u, x = self.wallet.get_balance()
        else:
            c, u, x = self.wallet.get_account_balance(account)
        out = {"confirmed": str(Decimal(c)/100000000)}
        if u:
            out["unconfirmed"] = str(Decimal(u)/100000000)
        if x:
            out["unmatured"] = str(Decimal(x)/100000000)
        return out

    def getaddressbalance(self, addr):
        out = self.network.synchronous_get([ ('blockchain.address.get_balance',[addr]) ])[0]
        out["confirmed"] =  str(Decimal(out["confirmed"])/100000000)
        out["unconfirmed"] =  str(Decimal(out["unconfirmed"])/100000000)
        return out

    def getproof(self, addr):
        p = self.network.synchronous_get([ ('blockchain.address.get_proof',[addr]) ])[0]
        out = []
        for i,s in p:
            out.append(i)
        return out

    def getmerkle(self, txid, height):
        return self.network.synchronous_get([ ('blockchain.transaction.get_merkle', [txid, int(height)]) ])[0]

    def getservers(self):
        while not self.network.is_up_to_date():
            time.sleep(0.1)
        return self.network.get_servers()

    def version(self):
        import electrum  # Needs to stay here to prevent ciruclar imports
        return electrum.ELECTRUM_VERSION

    def getmpk(self):
        return self.wallet.get_master_public_keys()

    def getseed(self):
        s = self.wallet.get_mnemonic(self.password)
        return s.encode('utf8')

    def importprivkey(self, sec):
        try:
            addr = self.wallet.import_key(sec,self.password)
            out = "Keypair imported: ", addr
        except Exception as e:
            out = "Error: Keypair import failed: " + str(e)
        return out

    def sweep(self, privkey, to_address, fee = 0.0001):
        fee = int(Decimal(fee)*100000000)
        return Transaction.sweep([privkey], self.network, to_address, fee)

    def signmessage(self, address, message):
        return self.wallet.sign_message(address, message, self.password)

    def verifymessage(self, address, signature, message):
        return bitcoin.verify_message(address, signature, message)

    def _mktx(self, outputs, fee = None, change_addr = None, domain = None):
        for to_address, amount in outputs:
            if not is_valid(to_address):
                raise Exception("Invalid Bitcoin address", to_address)

        if change_addr:
            if not is_valid(change_addr):
                raise Exception("Invalid Bitcoin address", change_addr)

        if domain is not None:
            for addr in domain:
                if not is_valid(addr):
                    raise Exception("invalid Bitcoin address", addr)

                if not self.wallet.is_mine(addr):
                    raise Exception("address not in wallet", addr)

        for k, v in self.wallet.labels.items():
            if change_addr and v == change_addr:
                change_addr = k

        final_outputs = []
        for to_address, amount in outputs:
            for k, v in self.wallet.labels.items():
                if v == to_address:
                    to_address = k
                    print_msg("alias", to_address)
                    break

            amount = int(100000000*amount)
            final_outputs.append(('address', to_address, amount))

        if fee is not None: fee = int(100000000*fee)
        return self.wallet.mktx(final_outputs, self.password, fee , change_addr, domain)

    def _read_csv(self, csvpath):
        import csv
        outputs = []
        with open(csvpath, 'rb') as csvfile:
            csvReader = csv.reader(csvfile, delimiter=',')
            for row in csvReader:
                address, amount = row
                assert bitcoin.is_address(address)
                amount = Decimal(amount)
                outputs.append((address, amount))
        return outputs

    def mktx(self, to_address, amount, fee = None, change_addr = None, from_addr = None):
        domain = [from_addr] if from_addr else None
        tx = self._mktx([(to_address, amount)], fee, change_addr, domain)
        return tx

    def mktx_csv(self, path, fee = None, change_addr = None, from_addr = None):
        domain = [from_addr] if from_addr else None
        outputs = self._read_csv(path)
        tx = self._mktx(outputs, fee, change_addr, domain)
        return tx

    def payto(self, to_address, amount, fee = None, change_addr = None, from_addr = None):
        domain = [from_addr] if from_addr else None
        tx = self._mktx([(to_address, amount)], fee, change_addr, domain)
        r, h = self.wallet.sendtx( tx )
        return h

    def payto_csv(self, path, fee = None, change_addr = None, from_addr = None):
        domain = [from_addr] if from_addr else None
        outputs = self._read_csv(path)
        tx = self._mktx(outputs, fee, change_addr, domain)
        r, h = self.wallet.sendtx( tx )
        return h

    def history(self):
        balance = 0
        out = []
        for item in self.wallet.get_history():
            tx_hash, conf, value, timestamp, balance = item
            try:
                time_str = datetime.datetime.fromtimestamp( timestamp).isoformat(' ')[:-3]
            except Exception:
                time_str = "----"

            label, is_default_label = self.wallet.get_label(tx_hash)

            out.append({'txid':tx_hash, 'date':"%16s"%time_str, 'label':label, 'value':format_satoshis(value), 'confirmations':conf})
        return out

    def setlabel(self, key, label):
        self.wallet.set_label(key, label)

    def listcontacts(self):
        contacts = StoreDict(self.config, 'contacts')
        return contacts

    def searchcontacts(self, query):
        contacts = StoreDict(self.config, 'contacts')
        results = {}
        for key, value in contacts.items():
            if query.lower() in key.lower():
                results[key] = value
        return results

    def listaddresses(self, show_change=False, show_label=False, frozen=False, unused=False, funded=False, show_balance=False):
        out = []
        for addr in self.wallet.addresses(True):
            if frozen and not self.wallet.is_frozen(addr):
                continue
            if not show_change and self.wallet.is_change(addr):
                continue
            if unused and self.wallet.is_used(addr):
                continue
            if funded and self.wallet.is_empty(addr):
                continue
            item = addr
            if show_balance:
                item += ", "+ format_satoshis(sum(self.wallet.get_addr_balance(addr)))
            if show_label:
                item += ', ' + self.wallet.labels.get(addr,'')
            out.append(item)
        return out

    def gettransaction(self, tx_hash, deserialize=False):
        tx = self.wallet.transactions.get(tx_hash) if self.wallet else None
        if tx is None and self.network:
            raw = self.network.synchronous_get([('blockchain.transaction.get', [tx_hash])])[0]
            if raw:
                tx = Transaction(raw)
            else:
                raise BaseException("Unknown transaction")
        return tx.deserialize() if deserialize else tx

    def encrypt(self, pubkey, message):
        return bitcoin.encrypt_message(message, pubkey)

    def decrypt(self, pubkey, message):
        return self.wallet.decrypt_message(pubkey, message, self.password)
