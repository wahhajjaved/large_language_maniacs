import logging

logger=logging.getLogger(__name__)

class Streamer:
    '''
        Streams lines from given files into chunks of fixed size.
    '''

    def __init__(self,files_list):
        self.files=files_list
        self.__init_filename_iterator()
        self.curr_file=None
        self.__step_filename()

    def __del__(self):
        if self.curr_file:
            self.curr_file.close()

    def __init_filename_iterator(self):
        '''
            Sets filename iterator to the first of the files passed during
            initialisation.
        '''
        logger.debug(f"Initialising filename iterator.")
        self.filename_iter=iter(self.files)

    def __step_filename(self):
        '''
            Opens the next file in the iterator and closes the current one.
            If there are no files left, then the file pointer
            (self.curr_file) will be None.
        '''
        if self.curr_file:
            self.curr_file.close()

        try:
            self.curr_file=open(next(self.filename_iter),errors='ignore')
        except:
            logger.error(f"File iterator terminated.")
            self.curr_file=None

        logger.debug(f"Currently reading {self.curr_file}")

    def get_single_line(self):
        '''
            Gets a single line from the current file. If no files are open,
            the returns None.
        '''
        if self.curr_file:
            line=self.curr_file.readline()
            if line=='':
                self.__step_filename()
                return self.get_single_line()
            else:
                return line
        else:
            return None

    def get_chunk(self,chunk_size=1000):
        '''
            Get chunk_size lines from files.
        '''
        chunk=[]

        while len(chunk)!=chunk_size:
            line=self.get_single_line()
            if not line:
                break
            chunk.append(line)

        return chunk

    def get_generator(self):
        self.__init_filename_iterator()

        def _generator():
            while 1:
                line=self.get_single_line()
                if line==None:
                    break
                yield line

        return _generator()
