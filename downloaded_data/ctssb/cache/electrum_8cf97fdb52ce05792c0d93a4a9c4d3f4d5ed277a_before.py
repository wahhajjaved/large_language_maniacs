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


import hashlib, base64, ecdsa, re


def rev_hex(s):
    return s.decode('hex')[::-1].encode('hex')

def int_to_hex(i, length=1):
    s = hex(i)[2:].rstrip('L')
    s = "0"*(2*length - len(s)) + s
    return rev_hex(s)

def var_int(i):
    # https://en.bitcoin.it/wiki/Protocol_specification#Variable_length_integer
    if i<0xfd:
        return int_to_hex(i)
    elif i<=0xffff:
        return "fd"+int_to_hex(i,2)
    elif i<=0xffffffff:
        return "fe"+int_to_hex(i,4)
    else:
        return "ff"+int_to_hex(i,8)

def op_push(i):
    if i<0x4c:
        return int_to_hex(i)
    elif i<0xff:
        return '4c' + int_to_hex(i)
    elif i<0xffff:
        return '4d' + int_to_hex(i,2)
    else:
        return '4e' + int_to_hex(i,4)
    


Hash = lambda x: hashlib.sha256(hashlib.sha256(x).digest()).digest()
hash_encode = lambda x: x[::-1].encode('hex')
hash_decode = lambda x: x.decode('hex')[::-1]


# pywallet openssl private key implementation

def i2d_ECPrivateKey(pkey, compressed=False):
    if compressed:
        key = '3081d30201010420' + \
              '%064x' % pkey.secret + \
              'a081a53081a2020101302c06072a8648ce3d0101022100' + \
              '%064x' % _p + \
              '3006040100040107042102' + \
              '%064x' % _Gx + \
              '022100' + \
              '%064x' % _r + \
              '020101a124032200'
    else:
        key = '308201130201010420' + \
              '%064x' % pkey.secret + \
              'a081a53081a2020101302c06072a8648ce3d0101022100' + \
              '%064x' % _p + \
              '3006040100040107044104' + \
              '%064x' % _Gx + \
              '%064x' % _Gy + \
              '022100' + \
              '%064x' % _r + \
              '020101a144034200'
        
    return key.decode('hex') + i2o_ECPublicKey(pkey.pubkey, compressed)
    
def i2o_ECPublicKey(pubkey, compressed=False):
    # public keys are 65 bytes long (520 bits)
    # 0x04 + 32-byte X-coordinate + 32-byte Y-coordinate
    # 0x00 = point at infinity, 0x02 and 0x03 = compressed, 0x04 = uncompressed
    # compressed keys: <sign> <x> where <sign> is 0x02 if y is even and 0x03 if y is odd
    if compressed:
        if pubkey.point.y() & 1:
            key = '03' + '%064x' % pubkey.point.x()
        else:
            key = '02' + '%064x' % pubkey.point.x()
    else:
        key = '04' + \
              '%064x' % pubkey.point.x() + \
              '%064x' % pubkey.point.y()
            
    return key.decode('hex')
            
# end pywallet openssl private key implementation

                                                
            
############ functions from pywallet ##################### 

def hash_160(public_key):
    try:
        md = hashlib.new('ripemd160')
        md.update(hashlib.sha256(public_key).digest())
        return md.digest()
    except:
        import ripemd
        md = ripemd.new(hashlib.sha256(public_key).digest())
        return md.digest()


def public_key_to_bc_address(public_key):
    h160 = hash_160(public_key)
    return hash_160_to_bc_address(h160)

def hash_160_to_bc_address(h160, addrtype = 0):
    vh160 = chr(addrtype) + h160
    h = Hash(vh160)
    addr = vh160 + h[0:4]
    return b58encode(addr)

def bc_address_to_hash_160(addr):
    bytes = b58decode(addr, 25)
    return ord(bytes[0]), bytes[1:21]

def encode_point(pubkey, compressed=False):
    order = generator_secp256k1.order()
    p = pubkey.pubkey.point
    x_str = ecdsa.util.number_to_string(p.x(), order)
    y_str = ecdsa.util.number_to_string(p.y(), order)
    if compressed:
        return chr(2 + (p.y() & 1)) + x_str
    else:
        return chr(4) + pubkey.to_string() #x_str + y_str

__b58chars = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
__b58base = len(__b58chars)

def b58encode(v):
    """ encode v, which is a string of bytes, to base58."""

    long_value = 0L
    for (i, c) in enumerate(v[::-1]):
        long_value += (256**i) * ord(c)

    result = ''
    while long_value >= __b58base:
        div, mod = divmod(long_value, __b58base)
        result = __b58chars[mod] + result
        long_value = div
    result = __b58chars[long_value] + result

    # Bitcoin does a little leading-zero-compression:
    # leading 0-bytes in the input become leading-1s
    nPad = 0
    for c in v:
        if c == '\0': nPad += 1
        else: break

    return (__b58chars[0]*nPad) + result

def b58decode(v, length):
    """ decode v into a string of len bytes."""
    long_value = 0L
    for (i, c) in enumerate(v[::-1]):
        long_value += __b58chars.find(c) * (__b58base**i)

    result = ''
    while long_value >= 256:
        div, mod = divmod(long_value, 256)
        result = chr(mod) + result
        long_value = div
    result = chr(long_value) + result

    nPad = 0
    for c in v:
        if c == __b58chars[0]: nPad += 1
        else: break

    result = chr(0)*nPad + result
    if length is not None and len(result) != length:
        return None

    return result


def EncodeBase58Check(vchIn):
    hash = Hash(vchIn)
    return b58encode(vchIn + hash[0:4])

def DecodeBase58Check(psz):
    vchRet = b58decode(psz, None)
    key = vchRet[0:-4]
    csum = vchRet[-4:]
    hash = Hash(key)
    cs32 = hash[0:4]
    if cs32 != csum:
        return None
    else:
        return key

def PrivKeyToSecret(privkey):
    return privkey[9:9+32]

def SecretToASecret(secret, compressed=False, addrtype=0):
    vchIn = chr((addrtype+128)&255) + secret
    if compressed: vchIn += '\01'
    return EncodeBase58Check(vchIn)

def ASecretToSecret(key, addrtype=0):
    vch = DecodeBase58Check(key)
    if vch and vch[0] == chr((addrtype+128)&255):
        return vch[1:]
    else:
        return False

def regenerate_key(sec):
    b = ASecretToSecret(sec)
    if not b:
        return False
    b = b[0:32]
    secret = int('0x' + b.encode('hex'), 16)
    return EC_KEY(secret)

def GetPubKey(pubkey, compressed=False):
    return i2o_ECPublicKey(pubkey, compressed)

def GetPrivKey(pkey, compressed=False):
    return i2d_ECPrivateKey(pkey, compressed)

def GetSecret(pkey):
    return ('%064x' % pkey.secret).decode('hex')

def is_compressed(sec):
    b = ASecretToSecret(sec)
    return len(b) == 33


def address_from_private_key(sec):
    # rebuild public key from private key, compressed or uncompressed
    pkey = regenerate_key(sec)
    assert pkey

    # figure out if private key is compressed
    compressed = is_compressed(sec)
        
    # rebuild private and public key from regenerated secret
    private_key = GetPrivKey(pkey, compressed)
    public_key = GetPubKey(pkey.pubkey, compressed)
    address = public_key_to_bc_address(public_key)
    return address


########### end pywallet functions #######################

# secp256k1, http://www.oid-info.com/get/1.3.132.0.10
_p = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2FL
_r = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141L
_b = 0x0000000000000000000000000000000000000000000000000000000000000007L
_a = 0x0000000000000000000000000000000000000000000000000000000000000000L
_Gx = 0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798L
_Gy = 0x483ada7726a3c4655da4fbfc0e1108a8fd17b448a68554199c47d08ffb10d4b8L
curve_secp256k1 = ecdsa.ellipticcurve.CurveFp( _p, _a, _b )
generator_secp256k1 = ecdsa.ellipticcurve.Point( curve_secp256k1, _Gx, _Gy, _r )
oid_secp256k1 = (1,3,132,0,10)
SECP256k1 = ecdsa.curves.Curve("SECP256k1", curve_secp256k1, generator_secp256k1, oid_secp256k1 ) 

from ecdsa.util import string_to_number, number_to_string

def msg_magic(message):
    return "\x18Bitcoin Signed Message:\n" + chr( len(message) ) + message


class EC_KEY(object):
    def __init__( self, secret ):
        self.pubkey = ecdsa.ecdsa.Public_key( generator_secp256k1, generator_secp256k1 * secret )
        self.privkey = ecdsa.ecdsa.Private_key( self.pubkey, secret )
        self.secret = secret

    def sign_message(self, message, compressed, address):
        private_key = ecdsa.SigningKey.from_secret_exponent( self.secret, curve = SECP256k1 )
        public_key = private_key.get_verifying_key()
        signature = private_key.sign_digest( Hash( msg_magic(message) ), sigencode = ecdsa.util.sigencode_string )
        assert public_key.verify_digest( signature, Hash( msg_magic(message) ), sigdecode = ecdsa.util.sigdecode_string)
        for i in range(4):
            sig = base64.b64encode( chr(27 + i + (4 if compressed else 0)) + signature )
            try:
                self.verify_message( address, sig, message)
                return sig
            except:
                continue
        else:
            raise BaseException("error: cannot sign message")

    @classmethod
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
        h = Hash( msg_magic(message) )
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


###################################### BIP32 ##############################

def bip32_init(seed):
    import hmac
        
    I = hmac.new("Bitcoin seed", seed, hashlib.sha512).digest()

    print "seed", seed.encode('hex')
    master_secret = I[0:32]
    master_chain = I[32:]

    # public key
    curve = SECP256k1
    master_private_key = ecdsa.SigningKey.from_string( master_secret, curve = SECP256k1 )
    master_public_key = master_private_key.get_verifying_key()
    K = master_public_key.to_string()
    K_compressed = GetPubKey(master_public_key.pubkey,True)
    return master_secret, master_chain, K, K_compressed

    
def CKD(k, c, n):
    import hmac
    from ecdsa.util import string_to_number, number_to_string
    order = generator_secp256k1.order()
    keypair = EC_KEY(string_to_number(k))
    K = GetPubKey(keypair.pubkey,True)
    I = hmac.new(c, K + rev_hex(int_to_hex(n,4)).decode('hex'), hashlib.sha512).digest()
    k_n = number_to_string( (string_to_number(I[0:32]) * string_to_number(k)) % order , order )
    c_n = I[32:]
    return k_n, c_n


def CKD_prime(K, c, n):
    import hmac
    from ecdsa.util import string_to_number, number_to_string
    order = generator_secp256k1.order()

    K_public_key = ecdsa.VerifyingKey.from_string( K, curve = SECP256k1 )
    K_compressed = GetPubKey(K_public_key.pubkey,True)

    I = hmac.new(c, K_compressed + rev_hex(int_to_hex(n,4)).decode('hex'), hashlib.sha512).digest()

    #pubkey = ecdsa.ecdsa.Public_key( generator_secp256k1, string_to_number(I[0:32]) * K_public_key.pubkey.point )
    public_key = ecdsa.VerifyingKey.from_public_point( string_to_number(I[0:32]) * K_public_key.pubkey.point, curve = SECP256k1 )
    K_n = public_key.to_string()
    K_n_compressed = GetPubKey(public_key.pubkey,True)
    c_n = I[32:]

    return K_n, K_n_compressed, c_n



class DeterministicSequence:
    """  Privatekey(type,n) = Master_private_key + H(n|S|type)  """

    def __init__(self, master_public_key):
        self.master_public_key = master_public_key

    @classmethod
    def from_seed(klass, seed):
        curve = SECP256k1
        secexp = klass.stretch_key(seed)
        master_private_key = ecdsa.SigningKey.from_secret_exponent( secexp, curve = SECP256k1 )
        master_public_key = master_private_key.get_verifying_key().to_string().encode('hex')
        self = klass(master_public_key)
        return self

    @classmethod
    def stretch_key(self,seed):
        oldseed = seed
        for i in range(100000):
            seed = hashlib.sha256(seed + oldseed).digest()
        return string_to_number( seed )

    def get_sequence(self,n,for_change):
        return string_to_number( Hash( "%d:%d:"%(n,for_change) + self.master_public_key.decode('hex') ) )

    def get_pubkey(self, n, for_change):
        curve = SECP256k1
        z = self.get_sequence(n, for_change)
        master_public_key = ecdsa.VerifyingKey.from_string( self.master_public_key.decode('hex'), curve = SECP256k1 )
        pubkey_point = master_public_key.pubkey.point + z*curve.generator
        public_key2 = ecdsa.VerifyingKey.from_public_point( pubkey_point, curve = SECP256k1 )
        return '04' + public_key2.to_string().encode('hex')

    def get_private_key(self, n, for_change, seed):
        order = generator_secp256k1.order()
        secexp = self.stretch_key(seed)
        secexp = ( secexp + self.get_sequence(n,for_change) ) % order
        pk = number_to_string( secexp, generator_secp256k1.order() )
        compressed = False
        return SecretToASecret( pk, compressed )

    def check_seed(self, seed):
        curve = SECP256k1
        secexp = self.stretch_key(seed)
        master_private_key = ecdsa.SigningKey.from_secret_exponent( secexp, curve = SECP256k1 )
        master_public_key = master_private_key.get_verifying_key().to_string().encode('hex')
        if master_public_key != self.master_public_key:
            print_error('invalid password (mpk)')
            raise BaseException('Invalid password')

        return True

################################## transactions








class Transaction:
    
    def __init__(self, raw):
        self.raw = raw
        self.deserialize()
        self.inputs = self.d['inputs']
        self.outputs = self.d['outputs']
        self.outputs = map(lambda x: (x['address'],x['value']), self.outputs)
        
    @classmethod
    def from_io(klass, inputs, outputs):
        raw = klass.serialize(inputs, outputs, for_sig = -1) # for_sig=-1 means do not sign
        self = klass(raw)
        self.inputs = inputs
        self.outputs = outputs
        return self

    def __str__(self):
        return self.raw

    @classmethod
    def multisig_script(klass, public_keys, num=None):
        n = len(public_keys)
        if num is None: num = n
        # supports only "2 of 2", and "2 of 3" transactions
        assert num <= n and n in [2,3]
    
        if num==2:
            s = '52'
        elif num == 3:
            s = '53'
        else:
            raise
    
        for k in public_keys:
            s += var_int(len(k)/2)
            s += k
        if n==2:
            s += '52'
        elif n==3:
            s += '53'
        else:
            raise
        s += 'ae'

        out = { "address": hash_160_to_bc_address(hash_160(s.decode('hex')), 5), "redeemScript":s }
        return out

    @classmethod
    def serialize( klass, inputs, outputs, for_sig = None ):

        s  = int_to_hex(1,4)                                         # version
        s += var_int( len(inputs) )                                  # number of inputs
        for i in range(len(inputs)):
            txin = inputs[i]
            s += txin['tx_hash'].decode('hex')[::-1].encode('hex')   # prev hash
            s += int_to_hex(txin['index'],4)                         # prev index

            if for_sig is None:
                pubkeysig = txin.get('pubkeysig')
                if pubkeysig:
                    pubkey, sig = pubkeysig[0]
                    sig = sig + chr(1)                               # hashtype
                    script  = op_push( len(sig))
                    script += sig.encode('hex')
                    script += op_push( len(pubkey))
                    script += pubkey.encode('hex')
                else:
                    signatures = txin['signatures']
                    pubkeys = txin['pubkeys']
                    script = '00'                                    # op_0
                    for sig in signatures:
                        sig = sig + '01'
                        script += op_push(len(sig)/2)
                        script += sig

                    redeem_script = klass.multisig_script(pubkeys,2)
                    script += op_push(len(redeem_script)/2)
                    script += redeem_script

            elif for_sig==i:
                if txin.get('redeemScript'):
                    script = txin['redeemScript']                    # p2sh uses the inner script
                else:
                    script = txin['raw_output_script']               # scriptsig
            else:
                script=''
            s += var_int( len(script)/2 )                            # script length
            s += script
            s += "ffffffff"                                          # sequence

        s += var_int( len(outputs) )                                 # number of outputs
        for output in outputs:
            addr, amount = output
            s += int_to_hex( amount, 8)                              # amount
            addrtype, hash_160 = bc_address_to_hash_160(addr)
            if addrtype == 0:
                script = '76a9'                                      # op_dup, op_hash_160
                script += '14'                                       # push 0x14 bytes
                script += hash_160.encode('hex')
                script += '88ac'                                     # op_equalverify, op_checksig
            elif addrtype == 5:
                script = 'a9'                                        # op_hash_160
                script += '14'                                       # push 0x14 bytes
                script += hash_160.encode('hex')
                script += '87'                                       # op_equal
            else:
                raise
            
            s += var_int( len(script)/2 )                           #  script length
            s += script                                             #  script
        s += int_to_hex(0,4)                                        #  lock time
        if for_sig is not None and for_sig != -1:
            s += int_to_hex(1, 4)                                   #  hash type
        return s


    def for_sig(self,i):
        return self.serialize(self.inputs, self.outputs, for_sig = i)


    def hash(self):
        return Hash(self.raw.decode('hex') )[::-1].encode('hex')

    def sign(self, private_keys):
        import deserialize

        for i in range(len(self.inputs)):
            txin = self.inputs[i]
            tx_for_sig = self.serialize( self.inputs, self.outputs, for_sig = i )

            if txin.get('redeemScript'):
                # 1 parse the redeem script
                num, redeem_pubkeys = deserialize.parse_redeemScript(txin.get('redeemScript'))
                self.inputs[i]["pubkeys"] = redeem_pubkeys

                # build list of public/private keys
                keypairs = {}
                for sec in private_keys.values():
                    compressed = is_compressed(sec)
                    pkey = regenerate_key(sec)
                    pubkey = GetPubKey(pkey.pubkey, compressed)
                    keypairs[ pubkey.encode('hex') ] = sec

                # list of already existing signatures
                signatures = txin.get("signatures",[])
                found = False
                complete = True

                # check if we have a key corresponding to the redeem script
                for pubkey in redeem_pubkeys:
                    public_key = ecdsa.VerifyingKey.from_string(pubkey[2:].decode('hex'), curve = SECP256k1)

                    for s in signatures:
                        try:
                            public_key.verify_digest( s.decode('hex')[:-1], Hash( tx_for_sig.decode('hex') ), sigdecode = ecdsa.util.sigdecode_der)
                            break
                        except ecdsa.keys.BadSignatureError:
                            continue
                    else:
                        if pubkey in keypairs.keys():
                            # add signature
                            sec = keypairs[pubkey]
                            compressed = is_compressed(sec)
                            pkey = regenerate_key(sec)
                            secexp = pkey.secret
                            private_key = ecdsa.SigningKey.from_secret_exponent( secexp, curve = SECP256k1 )
                            public_key = private_key.get_verifying_key()
                            sig = private_key.sign_digest( Hash( tx_for_sig.decode('hex') ), sigencode = ecdsa.util.sigencode_der )
                            assert public_key.verify_digest( sig, Hash( tx_for_sig.decode('hex') ), sigdecode = ecdsa.util.sigdecode_der)
                            signatures.append( sig.encode('hex') )
                            found = True
                        else:
                            complete = False
                        
                if not found:
                    raise BaseException("public key not found", keypairs.keys(), redeem_pubkeys)

                # for p2sh, pubkeysig is a tuple (may be incomplete)
                self.inputs[i]["signatures"] = signatures
                self.is_complete = complete

            else:
                sec = private_keys[txin['address']]
                compressed = is_compressed(sec)
                pkey = regenerate_key(sec)
                secexp = pkey.secret

                private_key = ecdsa.SigningKey.from_secret_exponent( secexp, curve = SECP256k1 )
                public_key = private_key.get_verifying_key()
                pkey = EC_KEY(secexp)
                pubkey = GetPubKey(pkey.pubkey, compressed)
                sig = private_key.sign_digest( Hash( tx_for_sig.decode('hex') ), sigencode = ecdsa.util.sigencode_der )
                assert public_key.verify_digest( sig, Hash( tx_for_sig.decode('hex') ), sigdecode = ecdsa.util.sigdecode_der)

                self.inputs[i]["pubkeysig"] = [(pubkey, sig)]
                self.is_complete = True

        self.raw = self.serialize( self.inputs, self.outputs )


    def deserialize(self):
        import deserialize
        vds = deserialize.BCDataStream()
        vds.write(self.raw.decode('hex'))
        self.d = deserialize.parse_Transaction(vds)
        return self.d
    

    def has_address(self, addr):
        found = False
        for txin in self.inputs:
            if addr == txin.get('address'): 
                found = True
                break
        for txout in self.outputs:
            if addr == txout[0]:
                found = True
                break
        return found


    def get_value(self, addresses, prevout_values):
        # return the balance for that tx
        is_send = False
        is_pruned = False
        v_in = v_out = v_out_mine = 0

        for item in self.inputs:
            addr = item.get('address')
            if addr in addresses:
                is_send = True
                key = item['prevout_hash']  + ':%d'%item['prevout_n']
                value = prevout_values.get( key )
                if value is None:
                    is_pruned = True
                else:
                    v_in += value
            else:
                is_pruned = True
                    
        for item in self.outputs:
            addr, value = item
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



def test_bip32():
    seed = "ff000000000000000000000000000000".decode('hex')
    master_secret, master_chain, master_public_key, master_public_key_compressed = bip32_init(seed)
        
    print "secret key", master_secret.encode('hex')
    print "chain code", master_chain.encode('hex')

    key_id = hash_160(master_public_key_compressed)
    print "keyid", key_id.encode('hex')
    print "base58"
    print "address", hash_160_to_bc_address(key_id)
    print "secret key", SecretToASecret(master_secret, True)

    print "-- m/0 --"
    k0, c0 = CKD(master_secret, master_chain, 0)
    print "secret", k0.encode('hex')
    print "chain", c0.encode('hex')
    print "secret key", SecretToASecret(k0, True)
    
    K0, K0_compressed, c0 = CKD_prime(master_public_key, master_chain, 0)
    print "address", hash_160_to_bc_address(hash_160(K0_compressed))
    
    print "-- m/0/1 --"
    K01, K01_compressed, c01 = CKD_prime(K0, c0, 1)
    print "address", hash_160_to_bc_address(hash_160(K01_compressed))
    
    print "-- m/0/1/3 --"
    K013, K013_compressed, c013 = CKD_prime(K01, c01, 3)
    print "address", hash_160_to_bc_address(hash_160(K013_compressed))
    
    print "-- m/0/1/3/7 --"
    K0137, K0137_compressed, c0137 = CKD_prime(K013, c013, 7)
    print "address", hash_160_to_bc_address(hash_160(K0137_compressed))
        


if __name__ == '__main__':
    test_bip32()


