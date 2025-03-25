# Eloipool - Python Bitcoin pool server
# Copyright (C) 2011-2012  Luke Dashjr <luke-jr+eloipool@utopios.org>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from binascii import b2a_hex
from bitcoin.script import countSigOps
from bitcoin.txn import Txn
from collections import deque
from copy import deepcopy
from queue import Queue
import jsonrpc
import logging
from math import log
from merkletree import MerkleTree
from struct import pack
import threading
from time import sleep, time
import traceback

_makeCoinbase = [0, 0]

class merkleMaker(threading.Thread):
	OldGMP = None
	GMPReq = {
		'capabilities': [
			'coinbasevalue',
			'coinbase/append',
			'coinbase',
			'generation',
			'time',
			'transactions/remove',
			'prevblock',
		],
		'tx': 'obj',
	}
	
	def __init__(self, *a, **k):
		super().__init__(*a, **k)
		self.daemon = True
		self.logger = logging.getLogger('merkleMaker')
		self.CoinbasePrefix = b''
		self.CoinbaseAux = {}
		self.isOverflowed = False
		self.lastWarning = {}
		self.MinimumTxnUpdateWait = 5
		self.overflowed = 0
		self.DifficultyChangeMod = 2016
	
	def _prepare(self):
		self.access = jsonrpc.ServiceProxy(self.UpstreamURI)
		
		self.currentBlock = (None, None, None)
		
		self.currentMerkleTree = None
		self.merkleRoots = deque(maxlen=self.WorkQueueSizeRegular[1])
		self.LowestMerkleRoots = self.WorkQueueSizeRegular[1]
		
		if not hasattr(self, 'WorkQueueSizeClear'):
			self.WorkQueueSizeClear = self.WorkQueueSizeLongpoll
		self._MaxClearSize = max(self.WorkQueueSizeClear[1], self.WorkQueueSizeLongpoll[1])
		self.clearMerkleTree = MerkleTree([self.clearCoinbaseTxn])
		self.clearMerkleRoots = Queue(self._MaxClearSize)
		self.LowestClearMerkleRoots = self.WorkQueueSizeClear[1]
		self.nextMerkleRoots = Queue(self._MaxClearSize)
		
		if not hasattr(self, 'WarningDelay'):
			self.WarningDelay = max(15, self.MinimumTxnUpdateWait * 2)
		if not hasattr(self, 'WarningDelayTxnLongpoll'):
			self.WarningDelayTxnLongpoll = self.WarningDelay
		if not hasattr(self, 'WarningDelayMerkleUpdate'):
			self.WarningDelayMerkleUpdate = self.WarningDelay
		
		self.lastMerkleUpdate = 0
		self.nextMerkleUpdate = 0
		global now
		now = time()
		self.updateMerkleTree()
	
	def updateBlock(self, newBlock, height = None, bits = None, _HBH = None):
		if newBlock == self.currentBlock[0]:
			if height in (None, self.currentBlock[1]) and bits in (None, self.currentBlock[2]):
				return
			if not self.currentBlock[2] is None:
				self.logger.error('Was working on block with wrong specs: %s (height: %d->%d; bits: %s->%s' % (
					b2a_hex(newBlock[::-1]).decode('utf8'),
					self.currentBlock[1],
					height,
					b2a_hex(self.currentBlock[2][::-1]).decode('utf8'),
					b2a_hex(bits[::-1]).decode('utf8'),
				))
		
		if height is None:
			height = self.currentBlock[1] + 1
		if bits is None:
			if height % self.DifficultyChangeMod == 1 or self.currentBlock[2] is None:
				self.logger.warning('New block: %s (height %d; bits: UNKNOWN)' % (b2a_hex(newBlock[::-1]).decode('utf8'), height))
			else:
				bits = self.currentBlock[2]
			
			# Pretend to be 1 lower height, so we possibly retain nextMerkleRoots
			height -= 1
			self.clearMerkleRoots = Queue(0)
		else:
			if _HBH is None:
				_HBH = (b2a_hex(newBlock[::-1]).decode('utf8'), b2a_hex(bits[::-1]).decode('utf8'))
			self.logger.info('New block: %s (height: %d; bits: %s)' % (_HBH[0], height, _HBH[1]))
			
			if self.currentBlock[1] != height:
				if self.currentBlock[1] == height - 1:
					self.clearMerkleRoots = self.nextMerkleRoots
				else:
					if self.currentBlock[1]:
						self.logger.warning('Change from height %d->%d; no longpoll merkleroots available!' % (self.currentBlock[1], height))
					self.clearMerkleRoots = Queue(self.WorkQueueSizeClear[1])
				self.nextMerkleRoots = Queue(self._MaxClearSize)
		self.merkleRoots.clear()
		self.currentMerkleTree = self.clearMerkleTree
		if self.currentBlock[0] != newBlock:
			self.lastBlock = self.currentBlock
		self.currentBlock = (newBlock, height, bits)
		self.needMerkle = 2
		self.onBlockChange()
	
	def _trimBlock(self, MP, txnlist, txninfo, floodn, msgf):
		fee = txninfo[-1].get('fee', None)
		if fee is None:
			raise self._floodCritical(now, floodn, doin=msgf('fees unknown'))
		if fee:
			# FIXME: coinbasevalue is *not* guaranteed to exist here
			MP['coinbasevalue'] -= fee
		
		txnlist[-1:] = ()
		txninfo[-1:] = ()
		
		return True
	
	def _APOT(self, txninfopot, MP, POTInfo):
		feeTxnsTrimmed = 0
		feesTrimmed = 0
		for txn in txninfopot:
			if txn.get('fee') is None:
				self._floodWarning(now, 'APOT-No-Fees', doin='Upstream didn\'t provide fee information required for aggressive POT', logf=self.logger.info)
				return
			if not txn['fee']:
				continue
			feesTrimmed += txn['fee']
			feeTxnsTrimmed += 1
		MP['coinbasevalue'] -= feesTrimmed
		
		POTInfo[2] = [feeTxnsTrimmed, feesTrimmed]
		self._floodWarning(now, 'POT-Trimming-Fees', doin='Aggressive POT trimming %d transactions with %d.%08d BTC total fees' % (feeTxnsTrimmed, feesTrimmed//100000000, feesTrimmed % 100000000), logf=self.logger.debug)
		
		return True
	
	def _makeBlockSafe(self, MP, txnlist, txninfo):
		blocksize = sum(map(len, txnlist)) + 80
		while blocksize > 934464:  # 1 "MB" limit - 64 KB breathing room
			txnsize = len(txnlist[-1])
			self._trimBlock(MP, txnlist, txninfo, 'SizeLimit', lambda x: 'Making blocks over 1 MB size limit (%d bytes; %s)' % (blocksize, x))
			blocksize -= txnsize
		
		# NOTE: This check doesn't work at all without BIP22 transaction obj format
		blocksigops = sum(a.get('sigops', 0) for a in txninfo)
		while blocksigops > 19488:  # 20k limit - 0x200 breathing room
			txnsigops = txninfo[-1]['sigops']
			self._trimBlock(MP, txnlist, txninfo, 'SigOpLimit', lambda x: 'Making blocks over 20k SigOp limit (%d; %s)' % (blocksigops, x))
			blocksigops -= txnsigops
		
		POTMode = getattr(self, 'POT', 1)
		txncount = len(txnlist) + 1
		if POTMode:
			feetxncount = txncount
			for i in range(txncount - 2, -1, -1):
				if 'fee' not in txninfo[i] or txninfo[i]['fee']:
					break
				feetxncount -= 1
			
			if getattr(self, 'Greedy', None):
				# Aim to cut off extra zero-fee transactions on the end
				# NOTE: not cutting out ones intermixed, in case of dependencies
				idealtxncount = feetxncount
			else:
				idealtxncount = txncount
			
			pot = 2**int(log(idealtxncount, 2))
			POTInfo = MP['POTInfo'] = [[idealtxncount, feetxncount, txncount], [pot, None], None]
			if pot < idealtxncount:
				if pot * 2 <= txncount:
					pot *= 2
				elif pot >= feetxncount:
					pass
				elif POTMode > 1 and self._APOT(txninfo[pot-1:], MP, POTInfo):
					# Trimmed even transactions with fees
					pass
				else:
					pot = idealtxncount
					self._floodWarning(now, 'Non-POT', doin='Making merkle tree with %d transactions (ideal: %d; max: %d)' % (pot, idealtxncount, txncount))
			POTInfo[1][1] = pot
			pot -= 1
			txnlist[pot:] = ()
			txninfo[pot:] = ()
	
	def updateMerkleTree(self):
		global now
		self.logger.debug('Polling bitcoind for memorypool')
		self.nextMerkleUpdate = now + self.TxnUpdateRetryWait
		
		try:
			MP = self.access.getmemorypool(self.GMPReq)
			self.OldGMP = False
			oMP = None
		except:
			MP = False
			try:
				oMP = self.access.getmemorypool()
			except:
				oMP = False
			if oMP is False:
				# This way, we get the error from the BIP22 call if the old one fails too
				raise
		if MP is False:
			# Pre-BIP22 server (bitcoind <0.7 or Eloipool <20120513)
			if not self.OldGMP:
				self.OldGMP = True
				self.logger.warning('Upstream server is not BIP 22 compliant')
			MP = oMP or self.access.getmemorypool()
		
		oMP = deepcopy(MP)
		
		prevBlock = bytes.fromhex(MP['previousblockhash'])[::-1]
		if 'height' in MP:
			height = MP['height']
		else:
			height = self.access.getinfo()['blocks'] + 1
		bits = bytes.fromhex(MP['bits'])[::-1]
		if (prevBlock, bits) != self.currentBlock:
			self.updateBlock(prevBlock, height, bits, _HBH=(MP['previousblockhash'], MP['bits']))
		
		txnlist = MP['transactions']
		if len(txnlist) and isinstance(txnlist[0], dict):
			txninfo = txnlist
			txnlist = tuple(a['data'] for a in txnlist)
			txninfo.insert(0, {
			})
		elif 'transactionfees' in MP:
			# Backward compatibility with pre-BIP22 gmp_fees branch
			txninfo = [{'fee':a} for a in MP['transactionfees']]
		else:
			# Backward compatibility with pre-BIP22 hex-only (bitcoind <0.7, Eloipool <future)
			txninfo = [{}] * len(txnlist)
		# TODO: cache Txn or at least txid from previous merkle roots?
		txnlist = [a for a in map(bytes.fromhex, txnlist)]
		
		self._makeBlockSafe(MP, txnlist, txninfo)
		
		cbtxn = self.makeCoinbaseTxn(MP['coinbasevalue'])
		cbtxn.setCoinbase(b'\0\0')
		cbtxn.assemble()
		txnlist.insert(0, cbtxn.data)
		
		txnlist = [a for a in map(Txn, txnlist[1:])]
		txnlist.insert(0, cbtxn)
		txnlist = list(txnlist)
		newMerkleTree = MerkleTree(txnlist)
		if newMerkleTree.merkleRoot() != self.currentMerkleTree.merkleRoot():
			newMerkleTree.POTInfo = MP.get('POTInfo')
			newMerkleTree.oMP = oMP
			self.logger.debug('Updating merkle tree')
			self.currentMerkleTree = newMerkleTree
		self.lastMerkleUpdate = now
		self.nextMerkleUpdate = now + self.MinimumTxnUpdateWait
		
		if self.needMerkle == 2:
			self.needMerkle = 1
			self.needMerkleSince = now
	
	def makeCoinbase(self):
		now = int(time())
		if now > _makeCoinbase[0]:
			_makeCoinbase[0] = now
			_makeCoinbase[1] = 0
		else:
			_makeCoinbase[1] += 1
		rv = self.CoinbasePrefix
		rv += pack('>L', now) + pack('>Q', _makeCoinbase[1]).lstrip(b'\0')
		# NOTE: Not using varlenEncode, since this is always guaranteed to be < 100
		rv = bytes( (len(rv),) ) + rv
		for v in self.CoinbaseAux.values():
			rv += v
		if len(rv) > 95:
			t = time()
			if self.overflowed < t - 300:
				self.logger.warning('Overflowing coinbase data! %d bytes long' % (len(rv),))
				self.overflowed = t
				self.isOverflowed = True
			rv = rv[:95]
		else:
			self.isOverflowed = False
		return rv
	
	def makeMerkleRoot(self, merkleTree, height):
		cbtxn = merkleTree.data[0]
		cb = self.makeCoinbase()
		cbtxn.setCoinbase(cb, height=height)
		cbtxn.assemble()
		merkleRoot = merkleTree.merkleRoot()
		return (merkleRoot, merkleTree, cbtxn.getCoinbase())
	
	_doing_last = None
	def _doing(self, what):
		if self._doing_last == what:
			self._doing_i += 1
			return
		global now
		if self._doing_last:
			self.logger.debug("Switching from (%4dx in %5.3f seconds) %s => %s" % (self._doing_i, now - self._doing_s, self._doing_last, what))
		self._doing_last = what
		self._doing_i = 1
		self._doing_s = now
	
	def _floodWarning(self, now, wid, wmsgf = None, doin = True, logf = None):
		if doin is True:
			doin = self._doing_last
			def a(f = wmsgf):
				return lambda: "%s (doing %s)" % (f(), doin)
			wmsgf = a()
		winfo = self.lastWarning.setdefault(wid, [0, None])
		(lastTime, lastDoing) = winfo
		if now <= lastTime + max(5, self.MinimumTxnUpdateWait) and doin == lastDoing:
			return
		winfo[0] = now
		nowDoing = doin
		winfo[1] = nowDoing
		if logf is None:
			logf = self.logger.warning
		logf(wmsgf() if wmsgf else doin)
	
	def makeClear(self):
		self._doing('clear merkle roots')
		self.clearMerkleRoots.put(self.makeMerkleRoot(self.clearMerkleTree, height=self.currentBlock[1]))
	
	def makeNext(self):
		self._doing('longpoll merkle roots')
		self.nextMerkleRoots.put(self.makeMerkleRoot(self.clearMerkleTree, height=self.currentBlock[1] + 1))
	
	def makeRegular(self):
		self._doing('regular merkle roots')
		self.merkleRoots.append(self.makeMerkleRoot(self.currentMerkleTree, height=self.currentBlock[1]))
	
	def merkleMaker_II(self):
		global now
		
		# No bits = no mining :(
		if self.currentBlock[2] is None:
			return self.updateMerkleTree()
		
		# First, ensure we have the minimum clear, next, and regular (in that order)
		if self.clearMerkleRoots.qsize() < self.WorkQueueSizeClear[0]:
			return self.makeClear()
		if self.nextMerkleRoots.qsize() < self.WorkQueueSizeLongpoll[0]:
			return self.makeNext()
		if len(self.merkleRoots) < self.WorkQueueSizeRegular[0]:
			return self.makeRegular()
		
		# If we've met the minimum requirements, consider updating the merkle tree
		if self.nextMerkleUpdate <= now:
			return self.updateMerkleTree()
		
		# Finally, fill up clear, next, and regular until we've met the maximums
		if self.clearMerkleRoots.qsize() < self.WorkQueueSizeClear[1]:
			return self.makeClear()
		if self.nextMerkleRoots.qsize() < self.WorkQueueSizeLongpoll[1]:
			return self.makeNext()
		if len(self.merkleRoots) < self.WorkQueueSizeRegular[1] or self.merkleRoots[0][1] != self.currentMerkleTree:
			return self.makeRegular()
		
		# Nothing left to do, fire onBlockUpdate event (if appropriate) and sleep
		if self.needMerkle == 1:
			self.onBlockUpdate()
			self.needMerkle = False
		self._doing('idle')
		# TODO: rather than sleepspin, block until MinimumTxnUpdateWait expires or threading.Condition(?)
		sleep(self.IdleSleepTime)
	
	def merkleMaker_I(self):
		global now
		now = time()
		
		self.merkleMaker_II()
		
		if self.needMerkle == 1 and now > self.needMerkleSince + self.WarningDelayTxnLongpoll:
			self._floodWarning(now, 'NeedMerkle', lambda: 'Transaction-longpoll requested %d seconds ago, and still not ready. Is your server fast enough to keep up with your configured WorkQueueSizeRegular maximum?' % (now - self.needMerkleSince,))
		if now > self.nextMerkleUpdate + self.WarningDelayMerkleUpdate:
			self._floodWarning(now, 'MerkleUpdate', lambda: "Haven't updated the merkle tree in at least %d seconds! Is your server fast enough to keep up with your configured work queue minimums?" % (now - self.lastMerkleUpdate,))
	
	def run(self):
		while True:
			try:
				self.merkleMaker_I()
			except:
				self.logger.critical(traceback.format_exc())
	
	def start(self, *a, **k):
		self._prepare()
		super().start(*a, **k)
	
	def getMRD(self):
		try:
			MRD = self.merkleRoots.pop()
			self.LowestMerkleRoots = min(len(self.merkleRoots), self.LowestMerkleRoots)
			rollPrevBlk = False
		except IndexError:
			qsz = self.clearMerkleRoots.qsize()
			if qsz < 0x10:
				self.logger.warning('clearMerkleRoots running out! only %d left' % (qsz,))
			MRD = self.clearMerkleRoots.get()
			self.LowestClearMerkleRoots = min(self.clearMerkleRoots.qsize(), self.LowestClearMerkleRoots)
			rollPrevBlk = True
		(merkleRoot, merkleTree, cb) = MRD
		(prevBlock, height, bits) = self.currentBlock
		return (merkleRoot, merkleTree, cb, prevBlock, bits, rollPrevBlk)
	
	def getMC(self):
		(prevBlock, bits) = self.currentBlock
		mt = self.currentMerkleTree
		cb = self.makeCoinbase()
		return (None, mt, cb, prevBlock, bits)

# merkleMaker tests
def _test():
	global now
	now = 1337039788
	MM = merkleMaker()
	reallogger = MM.logger
	class fakelogger:
		LO = False
		def critical(self, *a):
			if self.LO > 1: return
			reallogger.critical(*a)
		def warning(self, *a):
			if self.LO: return
			reallogger.warning(*a)
		def debug(self, *a):
			pass
	MM.logger = fakelogger()
	class NMTClass:
		pass
	
	# _makeBlockSafe tests
	from copy import deepcopy
	MP = {
		'coinbasevalue':50,
	}
	txnlist = [b'\0', b'\x01', b'\x02']
	txninfo = [{'fee':0, 'sigops':1}, {'fee':5, 'sigops':10000}, {'fee':0, 'sigops':10001}]
	def MBS(LO = 0):
		m = deepcopy( (MP, txnlist, txninfo) )
		MM.logger.LO = LO
		try:
			MM._makeBlockSafe(*m)
		except:
			if LO < 2:
				raise
		else:
			assert LO < 2  # An expected error wasn't thrown
		if 'POTInfo' in m[0]:
			del m[0]['POTInfo']
		return m
	MM.POT = 0
	assert MBS() == (MP, txnlist[:2], txninfo[:2])
	txninfo[2]['fee'] = 1
	MPx = deepcopy(MP)
	MPx['coinbasevalue'] -= 1
	assert MBS() == (MPx, txnlist[:2], txninfo[:2])
	txninfo[2]['sigops'] = 1
	assert MBS(1) == (MP, txnlist, txninfo)
	# APOT tests
	MM.POT = 2
	txnlist.append(b'\x03')
	txninfo.append({'fee':1, 'sigops':0})
	MPx = deepcopy(MP)
	MPx['coinbasevalue'] -= 1
	assert MBS() == (MPx, txnlist[:3], txninfo[:3])

_test()
