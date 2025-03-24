#!/usr/bin/env python2
# coding=utf-8
from __future__ import print_function

import re
import os
import pickle
from time import time

import requests

from util import logger
from command.config import global_config

BAIDUPAN_SERVER = "http://pan.baidu.com/api/"


class Pan(object):
    headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko)'
                      ' Chrome/37.0.2062.120 Safari/537.36'
    }

    def __init__(self):
        self.baiduid = ''
        self.bduss = ''
        self.bdstoken = ''
        self.session = requests.Session()
        self.cookies = self.session.cookies
        self._load_cookies_from_file()

    def _load_cookies_from_file(self):
        """Load cookies file if file exist."""
        if os.access(global_config.cookies, os.F_OK):
            with open(global_config.cookies) as f:
                cookies = requests.utils.cookiejar_from_dict(pickle.load(f))
            self.session.cookies = cookies
            # NOT SURE stoken is bdstoken!
            # self.token = self.session.cookies.get('STOKEN')
            self.baiduid = self.cookies.get('BAIDUID')
            self.bduss = self.cookies.get('BDUSS')
            return True
        return False

    def _save_img(self, img_url):
        """Download vcode image and save it to path of source code."""
        r = self.session.get(img_url)
        data = r.content
        img_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'vcode.jpg')
        with open(img_path, mode='wb') as fp:
            fp.write(data)
        print("Saved verification code to ", os.path.dirname(os.path.abspath(__file__)))

    def _handle_captcha(self, bdstoken=None):
        url = BAIDUPAN_SERVER + 'getcaptcha'
        d = {}
        extra_params = {
            'prod': 'share',
        }
        if bdstoken:
            extra_params['bdstoken'] = bdstoken
        res = self._request(base_url=url, extra_params=extra_params)
        if res.ok:
            t = res.json()
            self._save_img(t['vcode_img'])
            vcode_input = raw_input("Please input the captcha:\n")
            d['vcode_str'] = t['vcode_str']
            d['vcode_input'] = vcode_input
        return d

    @staticmethod
    def _dict_to_utf8(dictionary):
        """Convert dictionary's value to utf-8"""
        if not isinstance(dictionary, dict):
            return
        for k, v in dictionary.items():
            if isinstance(v, unicode):
                dictionary[k] = v.encode('utf-8')

    def _get_js(self, link, secret=None):
        """Get javascript code in html which contains share files info
        :param link: netdisk sharing link(publib or private).
        :type link: str
        :return str or None
        """
        req = self.session.get(link)
        if 'init' in req.url:
            self.verify_passwd(req.url, secret)
            req = self.session.get(link)
        data = req.text
        js_pattern = re.compile('<script\stype="text/javascript">!function\(\)([^<]+)</script>', re.DOTALL)
        js = re.findall(js_pattern, data)
        return js[0] or None

    def get_dlink(self, link, secret=None):
        info = FileInfo()
        js = self._get_js(link, secret)
        if info.match(js):
            extra_params = dict(bdstoken=info.bdstoken, sign=info.sign, timestamp=str(int(time())))
            post_form = {
                'encrypt': '0',
                'product': 'share',
                'uk': info.uk,
                'primaryid': info.share_id,
                'fid_list': '[{0}]'.format(info.fid_list)
            }
            url = BAIDUPAN_SERVER + 'sharedownload'
            response = self._request('POST', url, extra_params=extra_params, post_data=post_form)
            if response.ok:
                _json = response.json()
                errno = _json['errno']
                while errno == -20:
                    verify_params = self._handle_captcha(info.bdstoken)
                    post_form.update(verify_params)
                    response = self._request('POST', url, extra_params=extra_params, post_data=post_form)
                    _json = response.json()
                    errno = _json['errno']
                logger.debug(_json, extra={'type': 'json', 'method': 'POST'})
                if errno == 0:
                    # FIXME: only support single file for now
                    dlink = _json['list'][0]['dlink']
                    setattr(info, 'dlink', dlink)
                else:
                    raise UnknownError
        return info

    def verify_passwd(self, url, secret=None):
        """
        Verify password if url is a private sharing.
        :param url: link of private sharing. ('init' must in url)
        :type url: str
        :param secret: password of the private sharing
        :type secret: str
        :return: None
        """
        if secret:
            pwd = secret
        else:
            # FIXME: Improve translation
            pwd = raw_input("Please input this sharing password\n")
        data = {'pwd': pwd, 'vcode': ''}
        url = "{0}&t={1}&".format(url.replace('init', 'verify'), int(time()))
        logger.debug(url, extra={'type': 'url', 'method': 'POST'})
        r = self.session.post(url=url, data=data, headers=self.headers)
        mesg = r.json
        logger.debug(mesg, extra={'type': 'JSON', 'method': 'POST'})
        errno = mesg.get('errno')
        if errno == -63:
            raise UnknownError
        elif errno == -9:
            raise VerificationError("提取密码错误\n")

    def _request(self, method='GET', base_url='', extra_params=None, post_data=None, **kwargs):
        """
        Send a request based on template.
        :param method: http method, GET or POST
        :param base_url: base url
        :param extra_params: extra params for url
        :type extra_params: dict
        :param post_data: post data. Ignore if method is GET
        :type post_data: dict
        :return: requests.models.Response or None if invainvalid
        """
        params = {
            'channel': 'chunlei',
            'clienttype': 0,
            'web': 1,
            'app_id': 250528,
            'bdstoken': self.cookies.get('STOKEN')
        }
        if isinstance(extra_params, dict):
            params.update(extra_params)
            self._dict_to_utf8(params)
        if method == 'GET' and base_url:
            response = self.session.get(base_url, params=params, headers=self.headers, **kwargs)
        elif method == 'POST' and base_url and post_data:
            response = self.session.post(base_url, data=post_data, params=params, headers=self.headers, **kwargs)
        else:
            response = None
        return response


class FileInfo(object):
    pattern = re.compile('yunData\.(\w+\s=\s"\w+");')
    filename_pattern = re.compile('"server_filename":"([^"]+)"', re.DOTALL)

    def __init__(self):
        self.share_id = None
        self.bdstoken = None
        self.uk = None
        self.bduss = None
        self.fid_list = None
        self.sign = None
        self.filename = None

    def __call__(self, js):
        return self.match(js)

    def __repr__(self):
        return '<FileInfo %r>' % self.share_id

    def match(self, js):
        _filename = re.search(self.filename_pattern, js)
        if _filename:
            self.filename = _filename.group(1)
        data = re.findall(self.pattern, js)
        if not data:
            return False
        yun_data = dict([i.split(' = ', 1) for i in data])
        logger.debug(yun_data, extra={'method': 'GET', 'type': 'javascript'})
        if 'single' not in yun_data.get('SHAREPAGETYPE') or '0' in yun_data.get('LOGINSTATUS'):
            return False
        self.uk = yun_data.get('MYUK').strip('"')
        # self.bduss = yun_data.get('MYBDUSS').strip('"')
        self.share_id = yun_data.get('SHARE_ID').strip('"')
        self.fid_list = yun_data.get('FS_ID').strip('"')
        self.sign = yun_data.get('SIGN').strip('"')
        self.bdstoken = yun_data.get('MYBDSTOKEN').strip('"')
        if self.bdstoken:
            return True
        return False


class VerificationError(Exception):
    pass


class GetFilenameError(Exception):
    pass


class UnknownError(Exception):
    pass


class DownloadError(Exception):
    pass


if __name__ == '__main__':
    pass
