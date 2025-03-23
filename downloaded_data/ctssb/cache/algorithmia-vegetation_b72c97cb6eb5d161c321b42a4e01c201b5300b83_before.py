import Algorithmia
from Algorithmia.errors import AlgorithmException
from .util import sanity 


def vegetation(data_file):
    f = data_file.getFile()
    return -1


def vegetation_dir(src):
    client = Algorithmia.client()
    
    src_dir = client.dir(src)
    if not src_dir.exists():
        raise AlgorithmException("src ({}) does not exist.".format(src))

    algo = client.algo('nocturne/segment/0d0646cbca4747a4d0b38f93e8acb41c5cef5c61').set_options(timeout=600)
    #segmented_images = 'data://.session/'
    segmented_images = 'data://.my/tmp'
    result = algo.pipe(dict(src=src, dst=segmented_images))

    if result['status'] is not 'ok':
        raise AlgorithmException("error segmenting images")

    seg_dir = client.dir(segmented_images)
    return [vegetation(img_loc) for img_loc in seg_dir.files()]


def apply(input):
    sanity(input)
    src_images = input['src']
    return {'percentage_vegetation': vegetation_dir(src_images)}
