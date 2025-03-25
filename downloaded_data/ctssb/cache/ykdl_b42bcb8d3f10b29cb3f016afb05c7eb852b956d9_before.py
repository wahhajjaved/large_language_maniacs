#!/usr/bin/env python

from ..util.html import get_content
from ..util.match import match1
from ..extractor import VideoExtractor

import json
import time
from random import random
from urllib.parse import urlparse

'''
Changelog:
    1. http://tv.sohu.com/upload/swf/20150604/Main.swf
        new api
'''


class SohuBase(VideoExtractor):

    supported_stream_types = [ 'oriVid', 'superVid', 'highVid', 'norVid' ]

    realurls = { 'oriVid': [], 'superVid': [], 'highVid': [], 'norVid': [], 'relativeId': []}

    def parser_info(self, info, stream, lvid):
        host = info['allot']
        prot = info['prot']
        tvid = info['tvid']
        data = info['data']
        size = sum(map(int,data['clipsBytes']))
        assert len(data['clipsURL']) == len(data['clipsBytes']) == len(data['su'])
        for new, clip, ck, in zip(data['su'], data['clipsURL'], data['ck']):
            clipURL = urlparse(clip).path
            self.realurls[stream].append('http://'+host+'/?prot=9&prod=flash&pt=1&file='+clipURL+'&new='+new +'&key='+ ck+'&vid='+str(self.vid)+'&uid='+str(int(time.time()*1000))+'&t='+str(random())+'&rb=1')
        self.streams[stream] = {'container': 'mp4', 'video_profile': stream, 'size' : size}
        self.stream_types.append(stream)

    def prepare(self, **kwargs):
        assert self.url or self.vid

        if self.url and not self.vid:
            html = get_content(self.url)
            self.vid = match1(html, '\/([0-9]+)\/v\.swf', '\&id=(\d+)')

        info = json.loads(get_content(self.apiurl % self.vid))

        if info['status'] == 1:
            data = info['data']
            self.title = data['tvName']
            for stream in self.supported_stream_types:
                lvid = data[stream]
                if lvid == 0:
                    continue
                if lvid != self.vid :
                    info = json.loads(get_content(self.apiurl % lvid))
                self.parser_info(info, stream, lvid)

    def extract(self, **kwargs):
        stream_id = self.param.stream_id or self.stream_types[0]


        urls = []
        for url in self.realurls[stream_id]:
            info = json.loads(get_content(url))
            urls.append(info['url'])
        self.streams[stream_id]['src'] = urls
