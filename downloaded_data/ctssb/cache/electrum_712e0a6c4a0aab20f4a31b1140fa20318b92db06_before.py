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
import base64
import os
import re
import hashlib
import copy
import operator
import ast
import threading
import random
import aes
import ecdsa
import Queue
import time

from ecdsa.util import string_to_number, number_to_string
from util import print_error, user_dir, format_satoshis
from bitcoin import *

# URL decode
_ud = re.compile('%([0-9a-hA-H]{2})', re.MULTILINE)
urldecode = lambda x: _ud.sub(lambda m: chr(int(m.group(1), 16)), x)

# AES encryption
EncodeAES = lambda secret, s: base64.b64encode(aes.encryptData(secret,s))
DecodeAES = lambda secret, e: aes.decryptData(secret, base64.b64decode(e))


from version import ELECTRUM_VERSION, SEED_VERSION


class Wallet:
    def __init__(self, config={}):

        self.config = config
        self.electrum_version = ELECTRUM_VERSION
        self.gap_limit_for_change = 3 # constant

        # saved fields
        self.seed_version          = config.get('seed_version', SEED_VERSION)
        self.gap_limit             = config.get('gap_limit', 5)
        self.use_change            = config.get('use_change',True)
        self.fee                   = int(config.get('fee',100000))
        self.num_zeros             = int(config.get('num_zeros',0))
        self.master_public_key     = config.get('master_public_key','')
        self.use_encryption        = config.get('use_encryption', False)
        self.addresses             = config.get('addresses', [])          # receiving addresses visible for user
        self.change_addresses      = config.get('change_addresses', [])   # addresses used as change
        self.seed                  = config.get('seed', '')               # encrypted
        self.labels                = config.get('labels', {})
        self.aliases               = config.get('aliases', {})            # aliases for addresses
        self.authorities           = config.get('authorities', {})        # trusted addresses
        self.frozen_addresses      = config.get('frozen_addresses',[])
        self.prioritized_addresses = config.get('prioritized_addresses',[])
        self.receipts              = config.get('receipts',{})            # signed URIs
        self.addressbook           = config.get('contacts', [])
        self.imported_keys         = config.get('imported_keys',{})
        self.history               = config.get('addr_history',{})        # address -> list(txid, height)
        self.transactions          = config.get('transactions',{})        # txid -> deserialised

        self.requested_amounts     = config.get('requested_amounts',{})   # txid -> deserialised

        # not saved
        self.prevout_values = {}     # my own transaction outputs
        self.spent_outputs = []
        self.receipt = None          # next receipt
        self.banner = ''

        # spv
        self.verifier = None

        # there is a difference between wallet.up_to_date and interface.is_up_to_date()
        # interface.is_up_to_date() returns true when all requests have been answered and processed
        # wallet.up_to_date is true when the wallet is synchronized (stronger requirement)
        
        self.up_to_date = False
        self.lock = threading.Lock()
        self.tx_event = threading.Event()

        if self.seed_version != SEED_VERSION:
            raise ValueError("This wallet seed is deprecated. Please run upgrade.py for a diagnostic.")

        for tx_hash in self.transactions.keys():
            self.update_tx_outputs(tx_hash)


    def set_up_to_date(self,b):
        with self.lock: self.up_to_date = b

    def is_up_to_date(self):
        with self.lock: return self.up_to_date

    def update(self):
        self.up_to_date = False
        self.interface.poke('synchronizer')
        while not self.is_up_to_date(): time.sleep(0.1)

    def import_key(self, sec, password):
        # try password
        try:
            seed = self.decode_seed(password)
        except:
            raise BaseException("Invalid password")

        # rebuild public key from private key, compressed or uncompressed
        pkey = regenerate_key(sec)
        if not pkey:
            return False
        
        # figure out if private key is compressed
        compressed = is_compressed(sec)
        
        # rebuild private and public key from regenerated secret
        private_key = GetPrivKey(pkey, compressed)
        public_key = GetPubKey(pkey.pubkey, compressed)
        address = public_key_to_bc_address(public_key)
        
        if address in self.all_addresses():
            raise BaseException('Address already in wallet')
        
        # store the originally requested keypair into the imported keys table
        self.imported_keys[address] = self.pw_encode(sec, password )
        return address
        

    def init_seed(self, seed):
        if self.seed: raise BaseException("a seed exists")
        if not seed: 
            seed = "%032x"%ecdsa.util.randrange( pow(2,128) ) 
        self.seed = seed 
        self.config.set_key('seed', self.seed, True)
        self.config.set_key('seed_version', self.seed_version, True)
        self.init_mpk(self.seed)

    def init_mpk(self,seed):
        # public key
        curve = SECP256k1
        secexp = self.stretch_key(seed)
        master_private_key = ecdsa.SigningKey.from_secret_exponent( secexp, curve = SECP256k1 )
        self.master_public_key = master_private_key.get_verifying_key().to_string().encode('hex')
        self.config.set_key('master_public_key', self.master_public_key, True)

    def all_addresses(self):
        return self.addresses + self.change_addresses + self.imported_keys.keys()

    def is_mine(self, address):
        return address in self.all_addresses()

    def is_change(self, address):
        return address in self.change_addresses

    def is_valid(self,addr):
        ADDRESS_RE = re.compile('[1-9A-HJ-NP-Za-km-z]{26,}\\Z')
        if not ADDRESS_RE.match(addr): return False
        try:
            addrtype, h = bc_address_to_hash_160(addr)
        except:
            return False
        return addr == hash_160_to_bc_address(h, addrtype)

    def stretch_key(self,seed):
        oldseed = seed
        for i in range(100000):
            seed = hashlib.sha256(seed + oldseed).digest()
        return string_to_number( seed )

    def get_sequence(self,n,for_change):
        return string_to_number( Hash( "%d:%d:"%(n,for_change) + self.master_public_key.decode('hex') ) )

    def get_private_key_base58(self, address, password):
        secexp, compressed = self.get_private_key(address, password)
        if secexp is None: return None
        pk = number_to_string( secexp, generator_secp256k1.order() )
        return SecretToASecret( pk, compressed )

    def get_private_key(self, address, password):
        """  Privatekey(type,n) = Master_private_key + H(n|S|type)  """
        order = generator_secp256k1.order()
        
        if address in self.imported_keys.keys():
            sec = self.pw_decode( self.imported_keys[address], password )
            if not sec: return None, None
            pkey = regenerate_key(sec)
            compressed = is_compressed(sec)
            secexp = pkey.secret
        
        else:
            if address in self.addresses:
                n = self.addresses.index(address)
                for_change = False
            elif address in self.change_addresses:
                n = self.change_addresses.index(address)
                for_change = True
            else:
                raise BaseException("unknown address")

            seed = self.pw_decode( self.seed, password)
            if not seed: return None
            secexp = self.stretch_key(seed)
            secexp = ( secexp + self.get_sequence(n,for_change) ) % order
            compressed = False
            pkey = EC_KEY(secexp)

        public_key = GetPubKey(pkey.pubkey, compressed)
        addr = public_key_to_bc_address(public_key)
        if addr != address:
            print_error('Invalid password with correct decoding')
            raise BaseException('Invalid password')

        return secexp, compressed

    def msg_magic(self, message):
        return "\x18Bitcoin Signed Message:\n" + chr( len(message) ) + message

    def sign_message(self, address, message, password):
        secexp, compressed = self.get_private_key(address, password)
        private_key = ecdsa.SigningKey.from_secret_exponent( secexp, curve = SECP256k1 )
        public_key = private_key.get_verifying_key()
        signature = private_key.sign_digest( Hash( self.msg_magic( message ) ), sigencode = ecdsa.util.sigencode_string )
        assert public_key.verify_digest( signature, Hash( self.msg_magic( message ) ), sigdecode = ecdsa.util.sigdecode_string)
        for i in range(4):
            sig = base64.b64encode( chr(27 + i + (4 if compressed else 0)) + signature )
            try:
                self.verify_message( address, sig, message)
                return sig
            except:
                continue
        else:
            raise BaseException("error: cannot sign message")


    def verify_message(self, address, signature, message):
        """ See http://www.secg.org/download/aid-780/sec1-v2.pdf for the math """
        from ecdsa import numbertheory, ellipticcurve, util
        import msqr
        curve = curve_secp256k1
        G = generator_secp256k1
        order = G.order()
        # extract r,s from signature
        sig = base64.b64decode(signature)
        if len(sig) != 65: raise BaseException("Wrong encoding")
        r,s = util.sigdecode_string(sig[1:], order)
        nV = ord(sig[0])
        if nV < 27 or nV >= 35:
            raise BaseException("Bad encoding")
        if nV >= 31:
            compressed = True
            nV -= 4
        else:
            compressed = False

        recid = nV - 27
        # 1.1
        x = r + (recid/2) * order
        # 1.3
        alpha = ( x * x * x  + curve.a() * x + curve.b() ) % curve.p()
        beta = msqr.modular_sqrt(alpha, curve.p())
        y = beta if (beta - recid) % 2 == 0 else curve.p() - beta
        # 1.4 the constructor checks that nR is at infinity
        R = ellipticcurve.Point(curve, x, y, order)
        # 1.5 compute e from message:
        h = Hash( self.msg_magic( message ) )
        e = string_to_number(h)
        minus_e = -e % order
        # 1.6 compute Q = r^-1 (sR - eG)
        inv_r = numbertheory.inverse_mod(r,order)
        Q = inv_r * ( s * R + minus_e * G )
        public_key = ecdsa.VerifyingKey.from_public_point( Q, curve = SECP256k1 )
        # check that Q is the public key
        public_key.verify_digest( sig[1:], h, sigdecode = ecdsa.util.sigdecode_string)
        # check that we get the original signing address
        addr = public_key_to_bc_address( encode_point(public_key, compressed) )
        if address != addr:
            raise BaseException("Bad signature")
    

    def create_new_address(self, for_change):
        n = len(self.change_addresses) if for_change else len(self.addresses)
        address = self.get_new_address(n, for_change)
        if for_change:
            self.change_addresses.append(address)
        else:
            self.addresses.append(address)
        self.history[address] = []
        return address
        
    def get_new_address(self, n, for_change):
        """   Publickey(type,n) = Master_public_key + H(n|S|type)*point  """
        curve = SECP256k1
        z = self.get_sequence(n, for_change)
        master_public_key = ecdsa.VerifyingKey.from_string( self.master_public_key.decode('hex'), curve = SECP256k1 )
        pubkey_point = master_public_key.pubkey.point + z*curve.generator
        public_key2 = ecdsa.VerifyingKey.from_public_point( pubkey_point, curve = SECP256k1 )
        address = public_key_to_bc_address( '04'.decode('hex') + public_key2.to_string() )
        print address
        return address
                                                                      

    def change_gap_limit(self, value):
        if value >= self.gap_limit:
            self.gap_limit = value
            self.save()
            self.interface.poke('synchronizer')
            return True

        elif value >= self.min_acceptable_gap():
            k = self.num_unused_trailing_addresses()
            n = len(self.addresses) - k + value
            self.addresses = self.addresses[0:n]
            self.gap_limit = value
            self.save()
            return True
        else:
            return False

    def num_unused_trailing_addresses(self):
        k = 0
        for a in self.addresses[::-1]:
            if self.history.get(a):break
            k = k + 1
        return k

    def min_acceptable_gap(self):
        # fixme: this assumes wallet is synchronized
        n = 0
        nmax = 0
        k = self.num_unused_trailing_addresses()
        for a in self.addresses[0:-k]:
            if self.history.get(a):
                n = 0
            else:
                n += 1
                if n > nmax: nmax = n
        return nmax + 1


    def address_is_old(self, address):
        age = -1
        h = self.history.get(address, [])
        if h == ['*']:
            return True
        for tx_hash, tx_height in h:
            if tx_height == 0:
                tx_age = 0
            else: 
                tx_age = self.verifier.height - tx_height + 1
            if tx_age > age:
                age = tx_age
        return age > 2


    def synchronize_sequence(self, addresses, n, for_change):
        new_addresses = []
        while True:
            if len(self.addresses) < n:
                new_addresses.append( self.create_new_address(for_change) )
                continue
            if map( lambda a: self.address_is_old(a), addresses[-n:] ) == n*[False]:
                break
            else:
                new_addresses.append( self.create_new_address(for_change) )
        return new_addresses
        

    def synchronize(self):
        if not self.master_public_key:
            return []
        new_addresses = []
        new_addresses += self.synchronize_sequence(self.addresses, self.gap_limit, False)
        new_addresses += self.synchronize_sequence(self.change_addresses, self.gap_limit_for_change, True)
        return new_addresses


    def is_found(self):
        return (len(self.change_addresses) > self.gap_limit_for_change ) or ( len(self.addresses) > self.gap_limit )

    def fill_addressbook(self):
        for tx_hash, tx in self.transactions.items():
            is_send, _, _ = self.get_tx_value(tx_hash)
            if is_send:
                for o in tx['outputs']:
                    addr = o.get('address')
                    if not self.is_mine(addr) and addr not in self.addressbook:
                        self.addressbook.append(addr)
        # redo labels
        # self.update_tx_labels()


    def get_address_flags(self, addr):
        flags = "C" if self.is_change(addr) else "I" if addr in self.imported_keys.keys() else "-" 
        flags += "F" if addr in self.frozen_addresses else "P" if addr in self.prioritized_addresses else "-"
        return flags
        

    def get_tx_value(self, tx_hash, addresses = None):
        # return the balance for that tx
        if addresses is None: addresses = self.all_addresses()
        with self.lock:
            is_send = False
            is_pruned = False
            v_in = v_out = v_out_mine = 0
            d = self.transactions.get(tx_hash)
            if not d: 
                return 0, 0, 0

            for item in d.get('inputs'):
                addr = item.get('address')
                if addr in addresses:
                    is_send = True
                    key = item['prevout_hash']  + ':%d'%item['prevout_n']
                    value = self.prevout_values.get( key )
                    if value is None:
                        is_pruned = True
                    else:
                        v_in += value
                else:
                    is_pruned = True
                    
            for item in d.get('outputs'):
                addr = item.get('address')
                value = item.get('value')
                v_out += value
                if addr in addresses:
                    v_out_mine += value

        if not is_pruned:
            # all inputs are mine:
            fee = v_out - v_in
            v = v_out_mine - v_in
        else:
            # some inputs are mine:
            fee = None
            if is_send:
                v = v_out_mine - v_out
            else:
                # no input is mine
                v = v_out_mine
            
        return is_send, v, fee


    def get_tx_details(self, tx_hash):
        import datetime
        if not tx_hash: return ''
        tx = self.transactions.get(tx_hash)
        is_mine, v, fee = self.get_tx_value(tx_hash)
        conf, timestamp = self.verifier.get_confirmations(tx_hash)

        if conf:
            time_str = datetime.datetime.fromtimestamp(timestamp).isoformat(' ')[:-3]
        else:
            time_str = 'pending'

        inputs = map(lambda x: x.get('address'), tx['inputs'])
        outputs = map(lambda x: x.get('address'), tx['outputs'])
        tx_details = "Transaction Details" +"\n\n" \
            + "Transaction ID:\n" + tx_hash + "\n\n" \
            + "Status: %d confirmations\n"%conf
        if is_mine:
            if fee: 
                tx_details += "Amount sent: %s\n"% format_satoshis(v-fee, False) \
                              + "Transaction fee: %s\n"% format_satoshis(fee, False)
            else:
                tx_details += "Amount sent: %s\n"% format_satoshis(v, False) \
                              + "Transaction fee: unknown\n"
        else:
            tx_details += "Amount received: %s\n"% format_satoshis(v, False) \

        tx_details += "Date: %s\n\n"%time_str \
            + "Inputs:\n-"+ '\n-'.join(inputs) + "\n\n" \
            + "Outputs:\n-"+ '\n-'.join(outputs)

        r = self.receipts.get(tx_hash)
        if r:
            tx_details += "\n_______________________________________" \
                + '\n\nSigned URI: ' + r[2] \
                + "\n\nSigned by: " + r[0] \
                + '\n\nSignature: ' + r[1]

        return tx_details

    
    def update_tx_outputs(self, tx_hash):
        tx = self.transactions.get(tx_hash)
        for item in tx.get('outputs'):
            value = item.get('value')
            key = tx_hash+ ':%d'%item.get('index')
            with self.lock:
                self.prevout_values[key] = value 

        for item in tx.get('inputs'):
            if self.is_mine(item.get('address')):
                key = item['prevout_hash'] + ':%d'%item['prevout_n']
                self.spent_outputs.append(key)


    def get_addr_balance(self, address):
        assert self.is_mine(address)
        h = self.history.get(address,[])
        if h == ['*']: return 0,0
        c = u = 0
        received_coins = []   # list of coins received at address

        for tx_hash, tx_height in h:
            d = self.transactions.get(tx_hash)
            if not d: continue
            for item in d.get('outputs'):
                addr = item.get('address')
                if addr == address:
                    key = tx_hash + ':%d'%item['index']
                    received_coins.append(key)

        for tx_hash, tx_height in h:
            d = self.transactions.get(tx_hash)
            if not d: continue
            v = 0

            for item in d.get('inputs'):
                addr = item.get('address')
                if addr == address:
                    key = item['prevout_hash']  + ':%d'%item['prevout_n']
                    value = self.prevout_values.get( key )
                    if key in received_coins: 
                        v -= value
                    
            for item in d.get('outputs'):
                addr = item.get('address')
                key = tx_hash + ':%d'%item['index']
                if addr == address:
                    v += item.get('value')

            if tx_height:
                c += v
            else:
                u += v
        return c, u

    def get_balance(self):
        conf = unconf = 0
        for addr in self.all_addresses(): 
            c, u = self.get_addr_balance(addr)
            conf += c
            unconf += u
        return conf, unconf


    def choose_tx_inputs( self, amount, fixed_fee, from_addr = None ):
        """ todo: minimize tx size """
        total = 0
        fee = self.fee if fixed_fee is None else fixed_fee

        coins = []
        prioritized_coins = []
        domain = [from_addr] if from_addr else self.all_addresses()
        for i in self.frozen_addresses:
            if i in domain: domain.remove(i)

        for i in self.prioritized_addresses:
            if i in domain: domain.remove(i)

        for addr in domain:
            h = self.history.get(addr, [])
            if h == ['*']: continue
            for tx_hash, tx_height in h:
                tx = self.transactions.get(tx_hash)
                for output in tx.get('outputs'):
                    if output.get('address') != addr: continue
                    key = tx_hash + ":%d" % output.get('index')
                    if key in self.spent_outputs: continue
                    output['tx_hash'] = tx_hash
                    coins.append(output)


        for addr in self.prioritized_addresses:
            h = self.history.get(addr, [])
            if h == ['*']: continue
            for tx_hash, tx_height in h:
                tx = self.transactions.get(tx_hash)
                for output in tx.get('outputs'):
                    if output.get('address') != addr: continue
                    key = tx_hash + ":%d" % output.get('index')
                    if key in self.spent_outputs: continue
                    output['tx_hash'] = tx_hash
                    prioritized_coins.append(output)


        inputs = []
        coins = prioritized_coins + coins

        for item in coins: 
            addr = item.get('address')
            v = item.get('value')
            total += v
            inputs.append((addr, v, item['tx_hash'], item['index'], item['raw_output_script'], [(None,None)] ))
            fee = self.fee*len(inputs) if fixed_fee is None else fixed_fee
            if total >= amount + fee: break
        else:
            #print "not enough funds: %s %s"%(format_satoshis(total), format_satoshis(fee))
            inputs = []
        return inputs, total, fee

    def add_tx_change( self, outputs, amount, fee, total, change_addr=None ):
        change_amount = total - ( amount + fee )
        if change_amount != 0:
            # normally, the update thread should ensure that the last change address is unused
            if not change_addr:
                change_addr = self.change_addresses[-self.gap_limit_for_change]
            # Insert the change output at a random position in the outputs
            posn = random.randint(0, len(outputs))
            outputs[posn:posn] = [( change_addr,  change_amount)]
        return outputs

    def sign_inputs( self, inputs, outputs, password ):
        s_inputs = []
        for i in range(len(inputs)):
            addr, v, p_hash, p_pos, p_scriptPubKey, _ = inputs[i]
            secexp, compressed = self.get_private_key(addr, password)
            private_key = ecdsa.SigningKey.from_secret_exponent( secexp, curve = SECP256k1 )
            public_key = private_key.get_verifying_key()

            pkey = EC_KEY(secexp)
            pubkey = GetPubKey(pkey.pubkey, compressed)

            tx = raw_tx( inputs, outputs, for_sig = i )
            sig = private_key.sign_digest( Hash( tx.decode('hex') ), sigencode = ecdsa.util.sigencode_der )
            assert public_key.verify_digest( sig, Hash( tx.decode('hex') ), sigdecode = ecdsa.util.sigdecode_der)
            s_inputs.append( (addr, v, p_hash, p_pos, p_scriptPubKey, [(pubkey, sig)] ) )
        return s_inputs

    def pw_encode(self, s, password):
        if password:
            secret = Hash(password)
            return EncodeAES(secret, s)
        else:
            return s

    def pw_decode(self, s, password):
        if password is not None:
            secret = Hash(password)
            try:
                d = DecodeAES(secret, s)
            except:
                raise BaseException('Invalid password')
            return d
        else:
            return s

    def decode_seed(self, password):
        seed = self.pw_decode(self.seed, password)

        # check decoded seed with master public key
        curve = SECP256k1
        secexp = self.stretch_key(seed)
        master_private_key = ecdsa.SigningKey.from_secret_exponent( secexp, curve = SECP256k1 )
        master_public_key = master_private_key.get_verifying_key().to_string().encode('hex')
        if master_public_key != self.master_public_key:
            print_error('invalid password (mpk)')
            raise BaseException('Invalid password')

        return seed


    def get_history(self, address):
        with self.lock:
            return self.history.get(address)

    def get_status(self, h):
        if not h: return None
        if h == ['*']: return '*'
        status = ''
        for tx_hash, height in h:
            status += tx_hash + ':%d:' % height
        return hashlib.sha256( status ).digest().encode('hex')



    def receive_tx_callback(self, tx_hash, tx):

        if not self.check_new_tx(tx_hash, tx):
            raise BaseException("error: received transaction is not consistent with history"%tx_hash)

        with self.lock:
            self.transactions[tx_hash] = tx

        tx_height = tx.get('height')
        if self.verifier and tx_height>0: 
            self.verifier.add(tx_hash, tx_height)

        self.update_tx_outputs(tx_hash)

        self.save()


    def receive_history_callback(self, addr, hist):

        if not self.check_new_history(addr, hist):
            raise BaseException("error: received history for %s is not consistent with known transactions"%addr)
            
        with self.lock:
            self.history[addr] = hist
            self.save()

        if hist != ['*']:
            for tx_hash, tx_height in hist:
                if tx_height>0:
                    # add it in case it was previously unconfirmed
                    if self.verifier: self.verifier.add(tx_hash, tx_height)
                    # set the height in case it changed
                    tx = self.transactions.get(tx_hash)
                    if tx:
                        if tx.get('height') != tx_height:
                            print_error( "changing height for tx", tx_hash )
                            tx['height'] = tx_height


    def get_tx_history(self):
        with self.lock:
            history = self.transactions.values()
        history.sort(key = lambda x: x.get('height') if x.get('height') else 1e12)
        result = []
    
        balance = 0
        for tx in history:
            is_mine, v, fee = self.get_tx_value(tx['tx_hash'])
            if v is not None: balance += v
        c, u = self.get_balance()

        if balance != c+u:
            v_str = format_satoshis( c+u - balance, True, self.num_zeros)
            result.append( ('', 1000, 0, c+u-balance, None, c+u-balance, None ) )

        balance = c + u - balance
        for tx in history:
            tx_hash = tx['tx_hash']
            conf, timestamp = self.verifier.get_confirmations(tx_hash) if self.verifier else (None, None)
            is_mine, value, fee = self.get_tx_value(tx_hash)
            if value is not None:
                balance += value

            result.append( (tx_hash, conf, is_mine, value, fee, balance, timestamp) )

        return result

    def get_transactions_at_height(self, height):
        with self.lock:
            values = self.transactions.values()[:]

        out = []
        for tx in values:
            if tx['height'] == height:
                out.append(tx['tx_hash'])
        return out


    def get_label(self, tx_hash):
        label = self.labels.get(tx_hash)
        is_default = (label == '') or (label is None)
        if is_default: label = self.get_default_label(tx_hash)
        return label, is_default

    def get_default_label(self, tx_hash):
        tx = self.transactions.get(tx_hash)
        default_label = ''
        if tx:
            is_mine, _, _ = self.get_tx_value(tx_hash)
            if is_mine:
                for o in tx['outputs']:
                    o_addr = o.get('address')
                    if not self.is_mine(o_addr):
                        try:
                            default_label = self.labels[o_addr]
                        except KeyError:
                            default_label = o_addr
            else:
                for o in tx['outputs']:
                    o_addr = o.get('address')
                    if self.is_mine(o_addr) and not self.is_change(o_addr):
                        break
                else:
                    for o in tx['outputs']:
                        o_addr = o.get('address')
                        if self.is_mine(o_addr):
                            break
                    else:
                        o_addr = None

                if o_addr:
                    dest_label = self.labels.get(o_addr)
                    try:
                        default_label = self.labels[o_addr]
                    except KeyError:
                        default_label = o_addr

        return default_label


    def mktx(self, outputs, label, password, fee=None, change_addr=None, from_addr= None):

        for address, x in outputs:
            assert self.is_valid(address)

        amount = sum( map(lambda x:x[1], outputs) )
        inputs, total, fee = self.choose_tx_inputs( amount, fee, from_addr )
        if not inputs:
            raise ValueError("Not enough funds")

        if not self.use_change and not change_addr:
            change_addr = inputs[-1][0]
            print_error( "Sending change to", change_addr )
        outputs = self.add_tx_change(outputs, amount, fee, total, change_addr)

        if not self.seed:
            return repr({'inputs':inputs, 'outputs':outputs})
        
        tx = self.signed_tx(inputs, outputs, password)

        for address, x in outputs:
            if address not in self.addressbook and not self.is_mine(address):
                self.addressbook.append(address)

        if label: 
            tx_hash = Hash(tx.decode('hex') )[::-1].encode('hex')
            self.labels[tx_hash] = label

        return tx

    def signed_tx(self, inputs, outputs, password):
        s_inputs = self.sign_inputs( inputs, outputs, password )
        tx = raw_tx( s_inputs, outputs )
        return tx

    def sendtx(self, tx):
        # synchronous
        h = self.send_tx(tx)
        self.tx_event.wait()
        return self.receive_tx(h)

    def send_tx(self, tx):
        # asynchronous
        self.tx_event.clear()
        tx_hash = Hash(tx.decode('hex') )[::-1].encode('hex')
        self.interface.send([('blockchain.transaction.broadcast', [tx])], 'synchronizer')
        return tx_hash

    def receive_tx(self,tx_hash):
        out = self.tx_result 
        if out != tx_hash:
            return False, "error: " + out
        if self.receipt:
            self.receipts[tx_hash] = self.receipt
            self.receipt = None
        return True, out


    def read_alias(self, alias):
        # this might not be the right place for this function.
        import urllib

        m1 = re.match('([\w\-\.]+)@((\w[\w\-]+\.)+[\w\-]+)', alias)
        m2 = re.match('((\w[\w\-]+\.)+[\w\-]+)', alias)
        if m1:
            url = 'https://' + m1.group(2) + '/bitcoin.id/' + m1.group(1) 
        elif m2:
            url = 'https://' + alias + '/bitcoin.id'
        else:
            return ''
        try:
            lines = urllib.urlopen(url).readlines()
        except:
            return ''

        # line 0
        line = lines[0].strip().split(':')
        if len(line) == 1:
            auth_name = None
            target = signing_addr = line[0]
        else:
            target, auth_name, signing_addr, signature = line
            msg = "alias:%s:%s:%s"%(alias,target,auth_name)
            print msg, signature
            self.verify_message(signing_addr, signature, msg)
        
        # other lines are signed updates
        for line in lines[1:]:
            line = line.strip()
            if not line: continue
            line = line.split(':')
            previous = target
            print repr(line)
            target, signature = line
            self.verify_message(previous, signature, "alias:%s:%s"%(alias,target))

        if not self.is_valid(target):
            raise ValueError("Invalid bitcoin address")

        return target, signing_addr, auth_name

    def update_password(self, seed, old_password, new_password):
        if new_password == '': new_password = None
        self.use_encryption = (new_password != None)
        self.seed = self.pw_encode( seed, new_password)
        self.config.set_key('seed', self.seed, True)
        for k in self.imported_keys.keys():
            a = self.imported_keys[k]
            b = self.pw_decode(a, old_password)
            c = self.pw_encode(b, new_password)
            self.imported_keys[k] = c
        self.save()

    def get_alias(self, alias, interactive = False, show_message=None, question = None):
        try:
            target, signing_address, auth_name = self.read_alias(alias)
        except BaseException, e:
            # raise exception if verify fails (verify the chain)
            if interactive:
                show_message("Alias error: " + str(e))
            return

        print target, signing_address, auth_name

        if auth_name is None:
            a = self.aliases.get(alias)
            if not a:
                msg = "Warning: the alias '%s' is self-signed.\nThe signing address is %s.\n\nDo you want to add this alias to your list of contacts?"%(alias,signing_address)
                if interactive and question( msg ):
                    self.aliases[alias] = (signing_address, target)
                else:
                    target = None
            else:
                if signing_address != a[0]:
                    msg = "Warning: the key of alias '%s' has changed since your last visit! It is possible that someone is trying to do something nasty!!!\nDo you accept to change your trusted key?"%alias
                    if interactive and question( msg ):
                        self.aliases[alias] = (signing_address, target)
                    else:
                        target = None
        else:
            if signing_address not in self.authorities.keys():
                msg = "The alias: '%s' links to %s\n\nWarning: this alias was signed by an unknown key.\nSigning authority: %s\nSigning address: %s\n\nDo you want to add this key to your list of trusted keys?"%(alias,target,auth_name,signing_address)
                if interactive and question( msg ):
                    self.authorities[signing_address] = auth_name
                else:
                    target = None

        if target:
            self.aliases[alias] = (signing_address, target)
            
        return target


    def parse_url(self, url, show_message, question):
        o = url[8:].split('?')
        address = o[0]
        if len(o)>1:
            params = o[1].split('&')
        else:
            params = []

        amount = label = message = signature = identity = ''
        for p in params:
            k,v = p.split('=')
            uv = urldecode(v)
            if k == 'amount': amount = uv
            elif k == 'message': message = uv
            elif k == 'label': label = uv
            elif k == 'signature':
                identity, signature = uv.split(':')
                url = url.replace('&%s=%s'%(k,v),'')
            else: 
                print k,v

        if label and self.labels.get(address) != label:
            if question('Give label "%s" to address %s ?'%(label,address)):
                if address not in self.addressbook and address not in self.all_addresses(): 
                    self.addressbook.append(address)
                self.labels[address] = label

        if signature:
            if re.match('^(|([\w\-\.]+)@)((\w[\w\-]+\.)+[\w\-]+)$', identity):
                signing_address = self.get_alias(identity, True, show_message, question)
            elif self.is_valid(identity):
                signing_address = identity
            else:
                signing_address = None
            if not signing_address:
                return
            try:
                self.verify_message(signing_address, signature, url )
                self.receipt = (signing_address, signature, url)
            except:
                show_message('Warning: the URI contains a bad signature.\nThe identity of the recipient cannot be verified.')
                address = amount = label = identity = message = ''

        if re.match('^(|([\w\-\.]+)@)((\w[\w\-]+\.)+[\w\-]+)$', address):
            payto_address = self.get_alias(address, True, show_message, question)
            if payto_address:
                address = address + ' <' + payto_address + '>'

        return address, amount, label, message, signature, identity, url



    def freeze(self,addr):
        if addr in self.all_addresses() and addr not in self.frozen_addresses:
            self.unprioritize(addr)
            self.frozen_addresses.append(addr)
            self.config.set_key('frozen_addresses', self.frozen_addresses, True)
            return True
        else:
            return False

    def unfreeze(self,addr):
        if addr in self.all_addresses() and addr in self.frozen_addresses:
            self.frozen_addresses.remove(addr)
            self.config.set_key('frozen_addresses', self.frozen_addresses, True)
            return True
        else:
            return False

    def prioritize(self,addr):
        if addr in self.all_addresses() and addr not in self.prioritized_addresses:
            self.unfreeze(addr)
            self.prioritized_addresses.append(addr)
            self.config.set_key('prioritized_addresses', self.prioritized_addresses, True)
            return True
        else:
            return False

    def unprioritize(self,addr):
        if addr in self.all_addresses() and addr in self.prioritized_addresses:
            self.prioritized_addresses.remove(addr)
            self.config.set_key('prioritized_addresses', self.prioritized_addresses, True)
            return True
        else:
            return False

    def save(self):
        s = {
            'use_encryption': self.use_encryption,
            'use_change': self.use_change,
            'fee': self.fee,
            'addresses': self.addresses,
            'change_addresses': self.change_addresses,
            'addr_history': self.history, 
            'labels': self.labels,
            'contacts': self.addressbook,
            'imported_keys': self.imported_keys,
            'aliases': self.aliases,
            'authorities': self.authorities,
            'receipts': self.receipts,
            'num_zeros': self.num_zeros,
            'frozen_addresses': self.frozen_addresses,
            'prioritized_addresses': self.prioritized_addresses,
            'gap_limit': self.gap_limit,
            'transactions': self.transactions,
            'requested_amounts': self.requested_amounts,
        }
        for k, v in s.items():
            self.config.set_key(k,v)
        self.config.save()

    def set_verifier(self, verifier):
        self.verifier = verifier

        # review stored transactions and send them to the verifier
        # (they are not necessarily in the history, because history items might have have been pruned)
        for tx_hash, tx in self.transactions.items():
            tx_height = tx.get('height')
            if tx_height <1:
                print_error( "skipping", tx_hash, tx_height )
                continue
            
            if tx_height>0:
                self.verifier.add(tx_hash, tx_height)

        # review transactions that are in the history
        for addr, hist in self.history.items():
            if hist == ['*']: continue
            for tx_hash, tx_height in hist:
                if tx_height>0:
                    # add it in case it was previously unconfirmed
                    self.verifier.add(tx_hash, tx_height)
                    # set the height in case it changed
                    tx = self.transactions.get(tx_hash)
                    if tx:
                        if tx.get('height') != tx_height:
                            print_error( "changing height for tx", tx_hash )
                            tx['height'] = tx_height


    def is_addr_in_tx(self, addr, tx):
        found = False
        for txin in tx.get('inputs'):
            if addr == txin.get('address'): 
                found = True
                break
        for txout in tx.get('outputs'):
            if addr == txout.get('address'): 
                found = True
                break
        return found


    def check_new_history(self, addr, hist):
        
        # check that all tx in hist are relevant
        if hist != ['*']:
            for tx_hash, height in hist:
                tx = self.transactions.get(tx_hash)
                if not tx: continue
                if not self.is_addr_in_tx(addr,tx):
                    return False

        # check that we are not "orphaning" a transaction
        old_hist = self.history.get(addr,[])
        if old_hist == ['*']: return True

        for tx_hash, height in old_hist:
            if tx_hash in map(lambda x:x[0], hist): continue
            found = False
            for _addr, _hist in self.history.items():
                if _addr == addr: continue
                if _hist == ['*']: continue
                _tx_hist = map(lambda x:x[0], _hist)
                if tx_hash in _tx_hist:
                    found = True
                    break

            if not found:
                tx = self.transactions.get(tx_hash)
                # tx might not be there
                if not tx: continue
                
                # already verified?
                if tx.get('height'):
                    continue
                # unconfirmed tx
                print_error("new history is orphaning transaction:", tx_hash)
                # check that all outputs are not mine, request histories
                ext_requests = []
                for o in tx.get('outputs'):
                    _addr = o.get('address')
                    # assert not self.is_mine(_addr)
                    ext_requests.append( ('blockchain.address.get_history', [_addr]) )

                ext_h = self.interface.synchronous_get(ext_requests)
                height = None
                for h in ext_h:
                    if h == ['*']: continue
                    for item in h:
                        if item.get('tx_hash') == tx_hash:
                            height = item.get('height')
                            tx['height'] = height
                if height:
                    print_error("found height for", tx_hash, height)
                    self.verifier.add(tx_hash, height)
                else:
                    print_error("removing orphaned tx from history", tx_hash)
                    self.transactions.pop(tx_hash)

        return True



    def check_new_tx(self, tx_hash, tx):
        # 1 check that tx is referenced in addr_history. 
        addresses = []
        for addr, hist in self.history.items():
            if hist == ['*']:continue
            for txh, height in hist:
                if txh == tx_hash: 
                    addresses.append(addr)

        if not addresses:
            return False

        # 2 check that referencing addresses are in the tx
        for addr in addresses:
            if not self.is_addr_in_tx(addr, tx):
                return False

        return True




class WalletSynchronizer(threading.Thread):


    def __init__(self, wallet, config):
        threading.Thread.__init__(self)
        self.daemon = True
        self.wallet = wallet
        self.interface = self.wallet.interface
        self.interface.register_channel('synchronizer')
        self.wallet.interface.register_callback('connected', lambda: self.wallet.set_up_to_date(False))
        self.wallet.interface.register_callback('connected', lambda: self.interface.send([('server.banner',[])],'synchronizer') )
        self.was_updated = True
        self.running = False
        self.lock = threading.Lock()

    def stop(self):
        with self.lock: self.running = False
        self.interface.poke('synchronizer')

    def is_running(self):
        with self.lock: return self.running

    def synchronize_wallet(self):
        new_addresses = self.wallet.synchronize()
        if new_addresses:
            self.subscribe_to_addresses(new_addresses)
            self.wallet.up_to_date = False
            return
            
        if not self.interface.is_up_to_date('synchronizer'):
            if self.wallet.is_up_to_date():
                self.wallet.set_up_to_date(False)
                self.was_updated = True
            return

        self.wallet.set_up_to_date(True)
        self.was_updated = True

    
    def subscribe_to_addresses(self, addresses):
        messages = []
        for addr in addresses:
            messages.append(('blockchain.address.subscribe', [addr]))
        self.interface.send( messages, 'synchronizer')


    def run(self):
        with self.lock: self.running = True

        requested_tx = []
        missing_tx = []
        requested_histories = {}

        # request any missing transactions
        for history in self.wallet.history.values():
            if history == ['*']: continue
            for tx_hash, tx_height in history:
                if self.wallet.transactions.get(tx_hash) is None and (tx_hash, tx_height) not in missing_tx:
                    missing_tx.append( (tx_hash, tx_height) )
        print_error("missing tx", missing_tx)

        # wait until we are connected, in case the user is not connected
        while not self.interface.is_connected:
            time.sleep(1)
        
        # request banner, because 'connected' event happens before this thread is started
        self.interface.send([('server.banner',[])],'synchronizer')

        # subscriptions
        self.subscribe_to_addresses(self.wallet.all_addresses())

        while self.is_running():
            # 1. send new requests
            self.synchronize_wallet()

            for tx_hash, tx_height in missing_tx:
                if (tx_hash, tx_height) not in requested_tx:
                    self.interface.send([ ('blockchain.transaction.get',[tx_hash, tx_height]) ], 'synchronizer')
                    requested_tx.append( (tx_hash, tx_height) )
            missing_tx = []

            if self.was_updated:
                self.interface.trigger_callback('updated')
                self.was_updated = False

            # 2. get a response
            r = self.interface.get_response('synchronizer')

            # poke sends None. (needed during stop)
            if not r: continue

            # 3. handle response
            method = r['method']
            params = r['params']
            result = r.get('result')
            error = r.get('error')
            if error:
                print "error", r
                continue

            if method == 'blockchain.address.subscribe':
                addr = params[0]
                if self.wallet.get_status(self.wallet.get_history(addr)) != result:
                    if requested_histories.get(addr) is None:
                        self.interface.send([('blockchain.address.get_history', [addr])], 'synchronizer')
                        requested_histories[addr] = result

            elif method == 'blockchain.address.get_history':
                addr = params[0]
                print_error("receiving history", addr, result)
                if result == ['*']:
                    assert requested_histories.pop(addr) == '*'
                    self.wallet.receive_history_callback(addr, result)
                else:
                    hist = []
                    # check that txids are unique
                    txids = []
                    for item in result:
                        tx_hash = item['tx_hash']
                        if tx_hash not in txids:
                            txids.append(tx_hash)
                            hist.append( (tx_hash, item['height']) )

                    if len(hist) != len(result):
                        raise BaseException("error: server sent history with non-unique txid", result)

                    # check that the status corresponds to what was announced
                    rs = requested_histories.pop(addr)
                    if self.wallet.get_status(hist) != rs:
                        raise BaseException("error: status mismatch: %s"%addr)
                
                    # store received history
                    self.wallet.receive_history_callback(addr, hist)

                    # request transactions that we don't have 
                    for tx_hash, tx_height in hist:
                        if self.wallet.transactions.get(tx_hash) is None:
                            if (tx_hash, tx_height) not in requested_tx and (tx_hash, tx_height) not in missing_tx:
                                missing_tx.append( (tx_hash, tx_height) )

            elif method == 'blockchain.transaction.get':
                tx_hash = params[0]
                tx_height = params[1]
                d = self.deserialize_tx(tx_hash, tx_height, result)
                self.wallet.receive_tx_callback(tx_hash, d)
                self.was_updated = True
                requested_tx.remove( (tx_hash, tx_height) )
                print_error("received tx:", d)

            elif method == 'blockchain.transaction.broadcast':
                self.wallet.tx_result = result
                self.wallet.tx_event.set()

            elif method == 'server.banner':
                self.wallet.banner = result
                self.interface.trigger_callback('banner')
            else:
                print_error("Error: Unknown message:" + method + ", " + repr(params) + ", " + repr(result) )

            if self.was_updated and not requested_tx:
                self.interface.trigger_callback('updated')
                self.was_updated = False


    def deserialize_tx(self, tx_hash, tx_height, raw_tx):

        assert tx_hash == hash_encode(Hash(raw_tx.decode('hex')))
        import deserialize
        vds = deserialize.BCDataStream()
        vds.write(raw_tx.decode('hex'))
        d = deserialize.parse_Transaction(vds)
        d['height'] = tx_height
        d['tx_hash'] = tx_hash
        return d

