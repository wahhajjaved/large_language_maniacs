from itertools import izip
import matplotlib.pyplot as plt
import numpy as np
import os
from cesarpy.io import get_all_file_names_from_dir
import skimage
import skimage.io
import skimage.color
try:
    import cv2
    use_cv2 = True
except ImportError, e:
    print "Warning: opencv couldn't be imported."
    use_cv2 = False

def show_image(img, name='image', waitkey_forever=True):
    if use_cv2:
        img_to_show = img.astype(np.uint8) if img.dtype != np.uint8 else img
        if img.dtype == bool:
            img_to_show *= 255
        cv2.imshow(name, img_to_show)
        if waitkey_forever:
            cv2.waitKey(-1)
    else:
        print "This method needs opencv. Use show_image2 instead."

def show_image2(img):
    if len(img.shape) == 2:
        plt.imshow(img, cmap=plt.cm.gray, interpolation='none')
    else:
        plt.imshow(img, interpolation='none')
    plt.show()

def put_in_255_range(im):
    if im.dtype == np.bool:
        return im.astype(np.uint8)*255
    maxv = im.max()
    minv = im.min()
    div = float(maxv-minv)
    if div == 0:
        result = im
    else:
        result = 255*((im-minv)/div)
    result = result.astype(np.uint8)
    return result

def rectify(img):
    return np.minimum(np.maximum(img, 0), 255)

def psnr(original, other):
    original = original.astype(float)/255
    other = other.astype(float)/255
    return -10*np.log10(np.mean((original-other)**2))

def add_noise(img, sigma):
    return rectify(img.astype(float)+sigma*np.random.randn(*img.shape)).astype(np.uint8)

def dall():
    cv2.destroyAllWindows()

def something2gray(im, rgb=True):
    if im.dtype != np.uint8:
        imdtype = im.dtype
        im = im.astype(np.uint8)
    else:
        imdtype = np.uint8
    if use_cv2:
        inds = [2,1,0] if rgb else [0,1,2]
        result = cv2.cvtColor(im[:,:,inds], cv2.COLOR_BGR2GRAY)
    else:
        inds = [0,1,2] if rgb else [2,1,0]
        result = np.round(skimage.color.rgb2gray(im[:,:,inds])*255).astype(np.uint8)
    if imdtype != np.uint8:
        result = result.astype(imdtype)
    return result

def bgr2gray(im):
    return something2gray(im, rgb=False)

def rgb2gray(im):
    return something2gray(im, rgb=True)

def gray2bgr(img):
    return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)

def load_img(path, gray=False, to_float=False, use_skimage=False):
    if use_cv2 and not use_skimage:
        if gray:
            flag = cv2.IMREAD_GRAYSCALE if cv2.__version__ == '3.0.0-alpha' else cv2.CV_LOAD_IMAGE_GRAYSCALE
            img = cv2.imread(path, flag)
        else:
            img = cv2.imread(path)
    else:
        img = skimage.io.imread(path, as_grey=gray)
        if gray and img.max() <= 1:
            img = np.round(255*img).astype(np.uint8)
    if to_float:
        img = img.astype(float)
    return img

def read_images_from_dir(dir_path, imgs_ext, gray=False, sort=True, use_skimage=False, inds=None, starting_from=0, stack3frames=False, smart_sort=True):
    files = get_all_file_names_from_dir(dir_path, imgs_ext, sort=sort, smart_sort=smart_sort)
    imgs = []
    if inds == None:
        inds = np.arange(starting_from,len(files))
    new_files = np.array(files)[inds]
    for f,i in izip(new_files,inds):
        img0 = load_img(os.path.join(dir_path, f), gray, use_skimage=use_skimage)
        if stack3frames:
            img1 = load_img(os.path.join(dir_path, files[max(i-1,0)]), gray, use_skimage=use_skimage)
            img2 = load_img(os.path.join(dir_path, files[max(i-2,0)]), gray, use_skimage=use_skimage)
            imgs.append(np.dstack((img0,img1,img2)))
        else:
            imgs.append(img0)
    return imgs

def apply_to_each_channel(img, func):
    if len(img.shape) == 2:
        return func(img)
    ch_list = []
    nch = img.shape[2]
    for i in xrange(nch):
        ch_list.append(func(img[:,:,i]))
    return np.dstack(tuple(ch_list))

def naive_zoom(image, s):
    if s == 1:
        return image.copy()
    n,m = image.shape[:2]
    if len(image.shape) == 3:
        result = np.empty((n*s,m*s,image.shape[2]))
    else:
        result = np.empty((n*s,m*s))
    for i in xrange(n):
        for j in xrange(m):
            i_s, j_s = i*s, j*s
            result[i_s:i_s+s,j_s:j_s+s] = image[i,j]
    return result

def get_random_crop(img, crop_size, img2=None, rand_state=None):
    if rand_state == None:
        rand_state = np.random.RandomState()
    n, m = img.shape[:2]
    nn, mm = n-crop_size+1, m-crop_size+1
    si = rand_state.randint(nn)
    sj = rand_state.randint(mm)
    crop1 = img[si:si+crop_size,sj:sj+crop_size]
    if img2 != None:
        crop2 = img2[si:si+crop_size,sj:sj+crop_size]
        result = (crop1, crop2)
    else:
        result = crop1
    return result

def mask2rect(mask):
    rs,cs = np.where(mask!=0)
    if rs.size != 0:
        maxy = rs.max()
        miny = rs.min()
    else:
        maxy = mask.shape[0]-1
        miny = 0
    if cs.size != 0:
        maxx = cs.max()
        minx = cs.min()
    else:
        maxx = mask.shape[1]-1
        minx = 0
    return (minx, miny, maxx+1, maxy+1)

def draw_unfilled_rectangle(img, rect, color):
    x1,y1,x2,y2 = rect
    img[y1,x1:x2] = color
    img[y2,x1:x2] = color
    img[y1:y2,x1] = color
    img[y1:y2,x2] = color
