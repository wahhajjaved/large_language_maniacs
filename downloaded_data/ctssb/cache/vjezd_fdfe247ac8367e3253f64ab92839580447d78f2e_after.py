# encoding: utf-8

# Copyright (c) 2014, Ondrej Balaz. All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# * Redistributions of source code must retain the above copyright notice, this
#   list of conditions and the following disclaimer.
# * Redistributions in binary form must reproduce the above copyright notice,
#   this list of conditions and the following disclaimer in the documentation
#   and/or other materials provided with the distribution.
# * Neither the name of the original author nor the names of contributors
#   may be used to endorse or promote products derived from this software
#   without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL <COPYRIGHT HOLDER> BE LIABLE FOR ANY
# DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

""" CUPS Printer Port
    =================
"""

import os
import tempfile
import time
import logging
logger = logging.getLogger(__name__)

import cups

from vjezd import APP_NAME
from vjezd import threads
from vjezd.models import Ticket
from vjezd.ports.printer.pdf import PDFPrinter


class CUPSPrinterTestError(Exception):
    """ Exception raised when port test fails.
    """
    pass


class CUPSPrinterJobError(Exception):
    """ Exception raised when unable to finish print job.
    """
    pass


class CUPSPrinter(PDFPrinter):
    """ CUPS printer.

        Prints ticket of given size to CUPS configured printer. Basically CUPS
        printer is build on top of PDF printer. PDF printer write method uses
        same helper method as PDF printer and just redirects the output file to 

        Configuration
        -------------
        Port accepts the following positional arguments:
        #. width - ticket width in milimeters
        #. height - ticket height in milimeters
        #. cups_printer_name - name of configured CUPS printer

        Full configuration line of CUPS printer is:
        ``printer=cups:width,height,cups_printer_name
    """

    #: Timeout in second to wait for print job success
    PRINT_TIMEOUT = 20


    def __init__(self, *args):
        """ Initialize CUPS printer.
        """
        self.width = 72
        self.height = 80
        self.cups_printer_name = None # use default printer
        self.cups_printer = None
        self.cups_conn = None

        if len(args) >= 1:
            self.width = int(args[0])
        if len(args) >= 2:
            self.height = int(args[1])
        if len(args) >= 3:
            self.cups_printer_name = args[2]

        logger.info('CUPS printer using: {} size={}x{}mm'.format(
            self.cups_printer_name or 'default', self.width, self.height))


    def test(self):
        """ Test whether CUPS connection can be established and if printer is
            present.
        """
        conn = cups.Connection()
        printer = None
        if self.cups_printer_name:
            printer = conn.getPrinters().get(self.cups_printer_name, None)
        else:
            printer = conn.getDefault()
        if not printer:
            raise CUPSPrinterTestError('Non-existent CUPS printer: {}'.format(
                self.cups_printer_name or 'default'))
        conn = None


    def open(self):
        """ Open CUPS connection and PDF file.
        """
        logger.info('Opening CUPS printer: {}'.format(
            self.cups_printer_name or 'default'))
        self.cups_conn = cups.Connection()
        if self.cups_printer_name:
            self.cups_printer = self.cups_printer_name
        else:
            self.cups_printer = self.cups_conn.getDefault()
            logger.debug('Using real CUPS printer: {}'.format(
                self.cups_printer))

        # Make temporary PDF file for document rendering
        fd, self.pdf_path = tempfile.mkstemp(
            prefix='{}_'.format(APP_NAME), suffix='.pdf')
        os.close(fd)
        logger.debug('Using PDF temp file: {}'.format(self.pdf_path))


    def close(self):
        """ Close CUPS connection and PDF file.
        """
        logger.info('Closing CUPS printer: {}'.format(
            self.cups_printer_name or 'default'))
        if self.is_open():
            self.cups_conn = None
            self.cups_printer = None
            if self.pdf_path:
                # Remove temporary PDF file
                logger.debug('Removing PDF temp file: {}'.format(
                    self.pdf_path))
                os.remove(self.pdf_path)


    def is_open(self):
        """ Checks whether the CUPS connection is open.
        """
        if self.cups_conn:
            return True
        return False


    def write(self, data):
        """ Print ticket.
        """
        # Generate PDF
        PDFPrinter.write(self, data)

        print(self.cups_printer)
        # Print PDF and block until ticket gets printed (or max timeout is
        # reached)
        timeout = 0
        job_id = self.cups_conn.printFile(
            printer=self.cups_printer,
            filename=self.pdf_path,
            title='ticket-{}'.format(data.code),
            options={})
        logger.debug('CUPS print job #{} submitted. Waiting'.format(job_id))
        while self.cups_conn.getJobs().get(job_id, None) is not None:
            # Wait for given amount of time but don't block over exiting
            if timeout >= self.PRINT_TIMEOUT or threads.exiting:
                if threads.exiting:
                    logger.warning('Exiting before valid ticket printed')
                raise CUPSPrinterJobError('CUPS print job #{} stalled!'.format(
                    job_id))
            time.sleep(1)
            timeout = timeout + 1


# Export port_class for port_factory()
port_class = CUPSPrinter
