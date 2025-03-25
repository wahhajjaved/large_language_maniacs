#!/usr/bin/env python
# usage: image_processor.py image1 image2 ...

import sys
import time
import os.path
import subprocess as sp

output = ''

def call(command):
    call = sp.Popen(command, stdout = sp.PIPE, stderr = sp.PIPE, shell = False)
    output = call.communicate()
    if call.wait() != 0:
        log.write(output[0] or output[1])
    return output[0]

def convert(image, new_image, top, bottom):
    call("convert -strip -alpha off -colorspace RGB -depth 8 -trim -bordercolor white -border 1% \
        -units PixelsPerInch -density 300 -resample 300 -resize 2049x2758> -resize 980x2000< \
        +repage -compress lzw".split() + [image, new_image])
    call("convert -gravity north -crop 100%x5%".split() + [new_image, top])
    call("convert -gravity south -crop 100%x5%".split() + [new_image, bottom])

def ocr(image, new_image, top, bottom):
    call(["tesseract", new_image, new_image])
    call(["tesseract", top, top])
    call(["tesseract", bottom, bottom])

def grep(image, new_image, top, bottom):
    global output
    label = call("grep -iE (fig|table)".split() + [new_image+".txt", top+".txt", bottom+".txt"]).split('\n')[0]
    if label != '':
        output += "error: "+label[label.rfind('/')+1:label.index(':')].replace('.txt','')+" contains label "+label[label.index(':')+1:]+'\n'

def prepare(images):
    global output
    if type(images) is not list:
        raise Exception(images + ' is not a list. please supply a list of images')
    for image in images:
        if os.path.isfile(image):
            new_image = image.replace('.eps', '.tif')
            top = new_image.replace('.tif', '_top.tif')
            bottom = new_image.replace('.tif', '_bottom.tif')
            for step in [convert, ocr, grep]:
                try: step(image, new_image, top, bottom)
                except Exception as ee: log.write('** error in ' + step.__name__ + ': ' + str(ee) + '\n')
            if image.endswith('.eps'):
                call(['rm', image, new_image+'.txt', top, top+'.txt', bottom, bottom+'.txt'])
            else:
                call(['rm', new_image+'.txt', top, top+'.txt', bottom, bottom+'.txt'])

if __name__ == '__main__':
    if len(sys.argv) == 1:
        sys.exit('usage: image_processor.py image1 image2 ...')
    log = open('/var/local/scripts/production/articleprep/log/image_log', 'a')
    log.write('-' * 80 + '\n' + time.strftime("%Y-%m-%d %H:%M:%S") + '  ' + ' '.join(sys.argv[1:]) + '\n')
    prepare(sys.argv[1:])
    log.write(output)
    log.close()
    print output
