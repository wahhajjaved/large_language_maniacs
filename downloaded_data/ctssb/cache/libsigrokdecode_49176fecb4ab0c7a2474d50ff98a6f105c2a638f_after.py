##
## This file is part of the libsigrokdecode project.
##
## Copyright (C) 2012-2014 Uwe Hermann <uwe@hermann-uwe.de>
##
## This program is free software; you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published by
## the Free Software Foundation; either version 2 of the License, or
## (at your option) any later version.
##
## This program is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with this program; if not, write to the Free Software
## Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301 USA
##

import sigrokdecode as srd

cmd_name = {
    # Normal commands (CMD)
    0:  'GO_IDLE_STATE',
    1:  'SEND_OP_COND',
    6:  'SWITCH_FUNC',
    8:  'SEND_IF_COND',
    9:  'SEND_CSD',
    10: 'SEND_CID',
    12: 'STOP_TRANSMISSION',
    13: 'SEND_STATUS',
    16: 'SET_BLOCKLEN',
    17: 'READ_SINGLE_BLOCK',
    18: 'READ_MULTIPLE_BLOCK',
    24: 'WRITE_BLOCK',
    25: 'WRITE_MULTIPLE_BLOCK',
    27: 'PROGRAM_CSD',
    28: 'SET_WRITE_PROT',
    29: 'CLR_WRITE_PROT',
    30: 'SEND_WRITE_PROT',
    32: 'ERASE_WR_BLK_START_ADDR',
    33: 'ERASE_WR_BLK_END_ADDR',
    38: 'ERASE',
    42: 'LOCK_UNLOCK',
    55: 'APP_CMD',
    56: 'GEN_CMD',
    58: 'READ_OCR',
    59: 'CRC_ON_OFF',
    # CMD60-63: Reserved for manufacturer

    # Application-specific commands (ACMD)
    13: 'SD_STATUS',
    18: 'Reserved for SD security applications',
    22: 'SEND_NUM_WR_BLOCKS',
    23: 'SET_WR_BLK_ERASE_COUNT',
    25: 'Reserved for SD security applications',
    26: 'Reserved for SD security applications',
    38: 'Reserved for SD security applications',
    41: 'SD_SEND_OP_COND',
    42: 'SET_CLR_CARD_DETECT',
    43: 'Reserved for SD security applications',
    44: 'Reserved for SD security applications',
    45: 'Reserved for SD security applications',
    46: 'Reserved for SD security applications',
    47: 'Reserved for SD security applications',
    48: 'Reserved for SD security applications',
    49: 'Reserved for SD security applications',
    51: 'SEND_SCR',
}

def ann_cmd_list():
    l = []
    for i in range(63 + 1):
        l.append(['cmd%d' % i, 'CMD%d' % i])
    return l

class Decoder(srd.Decoder):
    api_version = 1
    id = 'sdcard_spi'
    name = 'SD card (SPI mode)'
    longname = 'Secure Digital card (SPI mode)'
    desc = 'Secure Digital card (SPI mode) low-level protocol.'
    license = 'gplv2+'
    inputs = ['spi']
    outputs = ['sdcard_spi']
    probes = []
    optional_probes = []
    options = {}
    annotations = ann_cmd_list() + [
        ['cmd-token', 'Command token'],
        ['r1', 'R1 reply'],
        ['r1b', 'R1B reply'],
        ['r2', 'R2 reply'],
        ['r3', 'R3 reply'],
        ['r7', 'R7 reply'],
        ['bits', 'Bits'],
    ]
    annotation_rows = (
        ('bits', 'Bits', (70,)),
        ('cmd-reply', 'Commands/replies',
            tuple(range(0, 63 + 1)) + tuple(range(65, 69 + 1))),
        ('cmd-token', 'Command tokens', (64,)),
    )

    def __init__(self, **kwargs):
        self.state = 'IDLE'
        self.samplenum = 0
        self.ss, self.es = 0, 0
        self.bit_ss, self.bit_es = 0, 0
        self.cmd_ss, self.cmd_es = 0, 0
        self.cmd_token = []
        self.cmd_token_bits = []
        self.is_acmd = False # Indicates CMD vs. ACMD
        self.blocklen = 0
        self.read_buf = []

    def start(self):
        # self.out_python = self.register(srd.OUTPUT_PYTHON)
        self.out_ann = self.register(srd.OUTPUT_ANN)

    def putx(self, data):
        self.put(self.cmd_ss, self.cmd_es, self.out_ann, data)

    def putb(self, data):
        self.put(self.bit_ss, self.bit_es, self.out_ann, data)

    def handle_command_token(self, mosi, miso):
        # Command tokens (6 bytes) are sent (MSB-first) by the host.
        #
        # Format:
        #  - CMD[47:47]: Start bit (always 0)
        #  - CMD[46:46]: Transmitter bit (1 == host)
        #  - CMD[45:40]: Command index (BCD; valid: 0-63)
        #  - CMD[39:08]: Argument
        #  - CMD[07:01]: CRC7
        #  - CMD[00:00]: End bit (always 1)

        if len(self.cmd_token) == 0:
            self.cmd_ss = self.ss

        self.cmd_token.append(mosi)
        self.cmd_token_bits.append(self.mosi_bits)
        # TODO: Record MISO too?

        # All command tokens are 6 bytes long.
        if len(self.cmd_token) < 6:
            return

        self.cmd_es = self.es

        # Received all 6 bytes of the command token. Now decode it.

        t = self.cmd_token

        # CMD or ACMD?
        s = 'ACMD' if self.is_acmd else 'CMD'
        # TODO
        self.putx([64, [s + ': %02x %02x %02x %02x %02x %02x' % tuple(t)]])

        def tb(byte, bit):
            return self.cmd_token_bits[5 - byte][7 - bit]

        # Bits[47:47]: Start bit (always 0)
        bit, self.bit_ss, self.bit_es = tb(5, 7)[0], tb(5, 7)[1], tb(5, 7)[2]
        self.putb([70, ['Start bit: %d' % bit]])
        if bit != 0:
            # TODO
            self.putb([1, ['Warning: Start bit != 0']])

        # Bits[46:46]: Transmitter bit (1 == host)
        bit, self.bit_ss, self.bit_es = tb(5, 6)[0], tb(5, 6)[1], tb(5, 6)[2]
        self.putb([70, ['Transmitter bit: %d' % bit]])
        if bit != 1:
            # TODO
            self.putb([1, ['Warning: Transmitter bit != 1']])

        # Bits[45:40]: Command index (BCD; valid: 0-63)
        cmd = self.cmd_index = t[0] & 0x3f
        # TODO
        self.bit_ss, self.bit_es = tb(5, 5)[1], tb(5, 0)[2]
        self.putb([70, ['Command: %s%d (%s)' % (s, cmd, cmd_name[cmd])]])

        # Bits[39:8]: Argument
        self.arg = (t[1] << 24) | (t[2] << 16) | (t[3] << 8) | t[4]
        self.bit_ss, self.bit_es = tb(4, 7)[1], tb(1, 0)[2]
        self.putb([70, ['Argument: 0x%04x' % self.arg]])
        # TODO: Sanity check on argument? Must be per-cmd?

        # Bits[7:1]: CRC
        # TODO: Check CRC.
        crc = t[5] >> 1
        self.bit_ss, self.bit_es = tb(0, 7)[1], tb(0, 1)[2]
        self.putb([70, ['CRC: 0x%01x' % crc]])

        # Bits[0:0]: End bit (always 1)
        bit, self.bit_ss, self.bit_es = tb(0, 0)[0], tb(0, 0)[1], tb(0, 0)[2]
        self.putb([70, ['End bit: %d' % bit]])
        if bit != 1:
            # TODO
            self.putb([1, ['Warning: End bit != 1']])

        # Handle command.
        if cmd in (0, 1, 9, 16, 17, 41, 49, 55, 59):
            self.state = 'HANDLE CMD%d' % cmd

        # ...
        if self.is_acmd and cmd != 55:
            self.is_acmd = False

        self.cmd_token = []
        self.cmd_token_bits = []

    def handle_cmd0(self, ):
        # CMD0: GO_IDLE_STATE
        # TODO
        self.putx([0, ['CMD0: Card reset / idle state']])
        self.state = 'GET RESPONSE R1'

    def handle_cmd1(self):
        # CMD1: SEND_OP_COND
        # TODO
        hcs = (self.arg & (1 << 30)) >> 30
        self.putb([1, ['HCS bit = %d' % hcs]])
        self.state = 'GET RESPONSE R1'

    def handle_cmd9(self):
        # CMD9: SEND_CSD (128 bits / 16 bytes)
        if len(self.read_buf) == 0:
            self.cmd_ss = self.ss
        self.read_buf.append(self.miso)
        # FIXME
        ### if len(self.read_buf) < 16:
        if len(self.read_buf) < 16 + 4:
            return
        self.cmd_es = self.es
        self.read_buf = self.read_buf[4:] ### TODO: Document or redo.
        self.putx([9, ['CSD: %s' % self.read_buf]])
        # TODO: Decode all bits.
        self.read_buf = []
        ### self.state = 'GET RESPONSE R1'
        self.state = 'IDLE'

    def handle_cmd10(self):
        # CMD10: SEND_CID (128 bits / 16 bytes)
        self.read_buf.append(self.miso)
        if len(self.read_buf) < 16:
            return
        self.putx([10, ['CID: %s' % self.read_buf]])
        # TODO: Decode all bits.
        self.read_buf = []
        self.state = 'GET RESPONSE R1'

    def handle_cmd16(self):
        # CMD16: SET_BLOCKLEN
        self.blocklen = self.arg # TODO
        # TODO: Sanity check on block length.
        self.putx([16, ['Block length: %d' % self.blocklen]])
        self.state = 'GET RESPONSE R1'

    def handle_cmd17(self):
        # CMD17: READ_SINGLE_BLOCK
        if len(self.read_buf) == 0:
            self.cmd_ss = self.ss
        self.read_buf.append(self.miso)
        if len(self.read_buf) == 1:
            self.putx([0, ['Read block at address: 0x%04x' % self.arg]])
        if len(self.read_buf) < self.blocklen + 2: # FIXME
            return
        self.cmd_es = self.es
        self.read_buf = self.read_buf[2:] # FIXME
        self.putx([17, ['Block data: %s' % self.read_buf]])
        self.read_buf = []
        self.state = 'GET RESPONSE R1'

    def handle_cmd41(self):
        # ACMD41: SD_SEND_OP_COND
        self.state = 'GET RESPONSE R1'

    def handle_cmd49(self):
        self.state = 'GET RESPONSE R1'

    def handle_cmd55(self):
        # CMD55: APP_CMD
        self.is_acmd = True
        self.state = 'GET RESPONSE R1'

    def handle_cmd59(self):
        # CMD59: CRC_ON_OFF
        crc_on_off = self.arg & (1 << 0)
        s = 'on' if crc_on_off == 1 else 'off'
        self.putb([59, ['SD card CRC option: %s' % s]])
        self.state = 'GET RESPONSE R1'

    def handle_cid_register(self):
        # Card Identification (CID) register, 128bits

        cid = self.cid

        # Manufacturer ID: CID[127:120] (8 bits)
        mid = cid[15]

        # OEM/Application ID: CID[119:104] (16 bits)
        oid = (cid[14] << 8) | cid[13]

        # Product name: CID[103:64] (40 bits)
        pnm = 0
        for i in range(12, 8 - 1, -1):
            pnm <<= 8
            pnm |= cid[i]

        # Product revision: CID[63:56] (8 bits)
        prv = cid[7]

        # Product serial number: CID[55:24] (32 bits)
        psn = 0
        for i in range(6, 3 - 1, -1):
            psn <<= 8
            psn |= cid[i]

        # RESERVED: CID[23:20] (4 bits)

        # Manufacturing date: CID[19:8] (12 bits)
        # TODO

        # CRC7 checksum: CID[7:1] (7 bits)
        # TODO

        # Not used, always 1: CID[0:0] (1 bit)
        # TODO

    def handle_response_r1(self, res):
        # The R1 response token format (1 byte).
        # Sent by the card after every command except for SEND_STATUS.

        self.cmd_ss, self.cmd_es = self.ss, self.es
        self.putx([65, ['R1: 0x%02x' % res]])

        def putbit(bit, data):
            b = self.miso_bits[7 - bit]
            self.bit_ss, self.bit_es = b[1], b[2]
            self.putb([70, data])

        # Bit 0: 'In idle state' bit
        s = '' if (res & (1 << 0)) else 'not '
        putbit(0, ['Card is %sin idle state' % s])

        # Bit 1: 'Erase reset' bit
        s = '' if (res & (1 << 1)) else 'not '
        putbit(1, ['Erase sequence %scleared' % s])

        # Bit 2: 'Illegal command' bit
        s = 'I' if (res & (1 << 2)) else 'No i'
        putbit(2, ['%sllegal command detected' % s])

        # Bit 3: 'Communication CRC error' bit
        s = 'failed' if (res & (1 << 3)) else 'was successful'
        putbit(3, ['CRC check of last command %s' % s])

        # Bit 4: 'Erase sequence error' bit
        s = 'E' if (res & (1 << 4)) else 'No e'
        putbit(4, ['%srror in the sequence of erase commands' % s])

        # Bit 5: 'Address error' bit
        s = 'M' if (res & (1 << 4)) else 'No m'
        putbit(5, ['%sisaligned address used in command' % s])

        # Bit 6: 'Parameter error' bit
        s = '' if (res & (1 << 4)) else 'not '
        putbit(6, ['Command argument %soutside allowed range' % s])

        # Bit 7: Always set to 0
        putbit(7, ['Bit 7 (always 0)'])

        self.state = 'IDLE'

    def handle_response_r1b(self, res):
        # TODO
        pass

    def handle_response_r2(self, res):
        # TODO
        pass

    def handle_response_r3(self, res):
        # TODO
        pass

    # Note: Response token formats R4 and R5 are reserved for SDIO.

    # TODO: R6?

    def handle_response_r7(self, res):
        # TODO
        pass

    def decode(self, ss, es, data):
        ptype, mosi, miso = data

        # For now, only use DATA and BITS packets.
        if ptype not in ('DATA', 'BITS'):
            return

        # Store the individual bit values and ss/es numbers. The next packet
        # is guaranteed to be a 'DATA' packet belonging to this 'BITS' one.
        if ptype == 'BITS':
            self.miso_bits, self.mosi_bits = miso, mosi
            return

        self.ss, self.es = ss, es

        # State machine.
        if self.state == 'IDLE':
            # Ignore stray 0xff bytes, some devices seem to send those!?
            if mosi == 0xff: # TODO?
                return
            self.state = 'GET COMMAND TOKEN'
            self.handle_command_token(mosi, miso)
        elif self.state == 'GET COMMAND TOKEN':
            self.handle_command_token(mosi, miso)
        elif self.state.startswith('HANDLE CMD'):
            self.miso, self.mosi = miso, mosi
            # Call the respective handler method for the command.
            s = 'handle_cmd%s' % self.state[10:].lower()
            handle_cmd = getattr(self, s)
            handle_cmd()
        elif self.state.startswith('GET RESPONSE'):
            # Ignore stray 0xff bytes, some devices seem to send those!?
            if miso == 0xff: # TODO?
                return

            # Call the respective handler method for the response.
            s = 'handle_response_%s' % self.state[13:].lower()
            handle_response = getattr(self, s)
            handle_response(miso)

            self.state = 'IDLE'
        else:
            raise Exception('Invalid state: %s' % self.state)

