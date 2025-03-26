import hashlib

from osgeo import gdal

def md5sum(file_uri):
    """Get the MD5 hash for a single file.  The file is read in a
        memory-efficient fashion.

        Args:
            uri (string): a string uri to the file to be tested.

        Returns:
            An md5sum of the input file"""

    block_size = 2**20
    file_handler = open(file_uri, 'rb')  # open in binary to ensure compatibility
    md5 = hashlib.md5()
    while True:
        data = file_handler.read(block_size)
        if not data:
            break
        md5.update(data)
    return md5.hexdigest()


def main():
    pass

if __name__ == '__main__':
    main()
