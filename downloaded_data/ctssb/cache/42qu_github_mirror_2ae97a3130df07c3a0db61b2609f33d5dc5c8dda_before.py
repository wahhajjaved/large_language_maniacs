#!/usr/bin/env python
# -*- coding: utf-8 -*-
from fs import fs_set_jpg, fs_url_jpg, fs_file_jpg, fs_get_jpg
from kv import Kv
from cid import CID_ICO, CID_ICO96
from zkit.pic import pic_square, picopen, pic_zoom_inner, pic_fit_height_if_high
from pic import pic_new, pic_save
import Image
from config import FS_URL

ico = Kv('ico', 0)
ico96 = Kv('ico96', 0)
ico_pos = Kv('ico_pos')

PIC_FULL_SIZE = 721
ICO96_DEFAULT = '%s/img/jpg/u/96.jpg'%FS_URL
PIC_DEFAULT = '%s/img/jpg/u/%%s.jpg'%FS_URL

#show = PicShow.mc_get(id)
#if x is not None and y is not None and size and show:
#    pic_id = show.pic_id
#    img = picopen(fs_get(PIC_SHOW_PREFIX+"721", "%s.jpg"%pic_id))
#    if img is None:
#        return
#    img = pic_square(img, size, top_left=(x, y), size=size)
#    ver = show.ver + 1
#    pic_show_set_jpg_square(pic_id, img, ver)
#    show.ver = ver
#    show.save()
#
#    p = PicShowPos.get_or_create(id=id)
#    p.txt = "%s_%s_%s"%(x, y, size)
#    p.save()
#
#    mc_flush(show.man_id)
#fs_file_jpg

def ico_pos_new(id, pos=None):
    if pos == ico_pos.get(id):
        return

    f = ico.get(id)
    if not f:
        return

    pic = picopen(fs_get_jpg(PIC_FULL_SIZE, f))
    if not pic:
        return

    pic_id = pic_new(CID_ICO96, id)
    if pos:
        pos_tuple = pos.split('_')
        if len(pos_tuple) == 3:
            x, y, size = map(int, pos_tuple)
            if size:
                pic = pic_square(pic, size, top_left=(x, y), size=size)

    pic = pic_square(pic, 96, size=96)
    fs_set_jpg('96', pic_id, pic)
    ico_pos.set(id, pos or '')
    ico96.set(id, pic_id)
    from model.feed_po import mc_feed_user_dict
    mc_feed_user_dict.delete(current_user_id)

def ico_new(id, pic):
    pic_id = pic_new(CID_ICO, id)
    pic_save(pic_id, pic)
    ico_save(pic_id, pic)
    ico.set(id, pic_id)
    ico_pos_new(id)
    return pic_id

def ico_save(pic_id, pic):
    p1 = pic_fit_height_if_high(pic, PIC_FULL_SIZE, 406)
    fs_set_jpg(PIC_FULL_SIZE, pic_id, p1)

    p2 = pic_fit_height_if_high(pic, 470, 264)
    fs_set_jpg('470', pic_id, p2)

    p3 = pic_fit_height_if_high(pic, 219, 123)
    fs_set_jpg('219', pic_id, p3)

def pic_url(id, size='721'):
    f = ico.get(id)
    if f:
        return fs_url_jpg(size, f)

def ico_url(id):
    pic_id = ico96.get(id)
    if pic_id:
        return fs_url_jpg('96', pic_id)

def pic_url_with_default(id, size='721'):
    url = pic_url(id, size)
    return url or PIC_DEFAULT % size

def ico_url_with_default(id):
    url = ico_url(id)
    return url or ICO96_DEFAULT

def pic_url_bind_with_default(zsite_list, size):
    key = 'pic%s' % size
    for i in zsite_list:
        setattr(
            i,
            key,
            pic_url_with_default(i.id, size)
        )


if __name__ == '__main__':
    print ico_url(399)
    print pic_url(399)
