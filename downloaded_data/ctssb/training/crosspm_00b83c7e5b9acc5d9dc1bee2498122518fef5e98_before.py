# -*- coding: utf-8 -*-
import json
from datetime import datetime
import time
from crosspm.adapters.common import BaseAdapter
from artifactory import ArtifactoryPath
from crosspm.helpers.exceptions import *
from crosspm.helpers.package import Package
import os
import requests

CHUNK_SIZE = 1024

setup = {
    "name": [
        "artifactory",
        "jfrog-artifactory",
    ],
}


class Adapter(BaseAdapter):
    def get_packages(self, source, parser, downloader, list_or_file_path):
        _auth_type = source.args['auth_type'].lower() if 'auth_type' in source.args else 'simple'
        _art_auth = {}
        if 'auth' in source.args:
            if _auth_type == 'simple':
                _art_auth['auth'] = tuple(source.args['auth'])
            elif _auth_type == 'cert':
                _art_auth['cert'] = os.path.realpath(os.path.expanduser(source.args['auth']))
        if 'verify' in source.args:
            _art_auth['verify'] = source.args['verify'].lower in ['true', 'yes', '1']

        _pkg_name_col = self._config.name_column
        _packages_found = {}
        _pkg_name_old = ""
        for _paths in parser.get_paths(list_or_file_path, source):
            _packages = []
            _params_found = {}
            _pkg_name = _paths['params'][_pkg_name_col]
            if _pkg_name != _pkg_name_old:
                _pkg_name_old = _pkg_name
                self._log.info(
                    '{}: {}'.format(_pkg_name, {k: v for k, v in _paths['params'].items() if k != _pkg_name_col}))
            last_error = ''
            for _path in _paths['paths']:
                _path_fixed, _path_pattern = parser.split_fixed_pattern(_path)
                _repo_paths = ArtifactoryPath(_path_fixed, **_art_auth)
                try:
                    for _repo_path in _repo_paths.glob(_path_pattern):
                        _mark = 'found'
                        if parser.validate_path(str(_repo_path), _paths['params']):
                            _mark = 'match'
                            _valid, _params = parser.validate(_repo_path.properties, 'properties', _paths['params'],
                                                              return_params=True)
                            if _valid:
                                _mark = 'valid'
                                _packages += [_repo_path]
                                _params_found[_repo_path] = {k: v for k, v in _params.items()}
                        self._log.debug('  {}: {}'.format(_mark, str(_repo_path)))
                except RuntimeError as e:
                    try:
                        err = json.loads(e.args[0])
                    except:
                        err = {}
                    if isinstance(err, dict):
                        # TODO: Check errors
                        # e.args[0] = '''{
                        #                   "errors" : [ {
                        #                     "status" : 404,
                        #                     "message" : "Not Found"
                        #                   } ]
                        #                 }'''
                        for error in err.get('errors', []):
                            err_status = error.get('status', -1)
                            err_msg = error.get('message', '')
                            if err_status == 401:
                                msg = 'Authentication error[{}]{}'.format(err_status,
                                                                          (': {}'.format(err_msg)) if err_msg else '')
                            elif err_status == 404:
                                msg = last_error
                            else:
                                msg = 'Error[{}]{}'.format(err_status,
                                                           (': {}'.format(err_msg)) if err_msg else '')
                            if last_error != msg:
                                self._log.error(msg)
                            last_error = msg

            _package = None
            if _packages:
                _packages = parser.filter_one(_packages, _paths['params'])
                if type(_packages) is dict:
                    _packages = [_packages]

                if len(_packages) == 1:
                    # one package found: ok!
                    # _stat = _packages[0]['path'].stat()
                    # _stat = {k: getattr(_stat, k, None) for k in ('ctime',
                    #                                               'mtime',
                    #                                               'md5',
                    #                                               'sha1',
                    #                                               'size')}
                    _params_tmp = _params_found.get(_packages[0]['path'], {})
                    _params_tmp.update({k: v for k, v in _packages[0]['params'].items() if k not in _params_tmp})
                    _package = Package(_pkg_name, _packages[0]['path'], _paths['params'], downloader, self, parser,
                                       _params_tmp)  # , _stat)
                    _mark = 'chosen'
                    self._log.info('  {}: {}'.format(_mark, str(_packages[0]['path'])))

                elif len(_packages) > 1:
                    # TODO: multiple packages found: wtf?!
                    raise CrosspmException(
                        CROSSPM_ERRORCODE_MULTIPLE_DEPS,
                        'Multiple instances found for package [{}] not found.'.format(_pkg_name)
                    )
                else:
                    # Package not found: may be error, but it could be in other source.
                    pass
            else:
                # Package not found: may be error, but it could be in other source.
                pass
                # _pkg_name = self._config.get_column_name(0)
                # raise CrosspmException(
                #     CROSSPM_ERRORCODE_PACKAGE_NOT_FOUND,
                #     'Package [{}] not found.'.format(_pkg_name)
                # )
            if (_package is not None) or (not self._config.no_fails):
                _added, _package = downloader.add_package(_pkg_name, _package)
            else:
                _added = False
            if _package is not None:
                _pkg_name = _package.get_name_and_path(True)
            if _added or (_package is not None):
                if (_package is not None) or (not self._config.no_fails):
                    if (_package is not None) or (_packages_found.get(_pkg_name, None) is None):
                        _packages_found[_pkg_name] = _package

            if _added and (_package is not None):
                if downloader.do_load:
                    _package.download(downloader.packed_path)

                    _deps_file = _package.get_file(self._config.deps_lock_file_name, downloader.temp_path)
                    if _deps_file:
                        _package.find_dependencies(_deps_file)
                    elif self._config.deps_file_name:
                        _deps_file = _package.get_file(self._config.deps_file_name, downloader.temp_path)
                        if os.path.isfile(_deps_file):
                            _package.find_dependencies(_deps_file)

        return _packages_found

    def download_package(self, package, dest_path):
        _dest_file = os.path.join(dest_path, package.name)
        _stat_attr = {'ctime': 'st_atime',
                      'mtime': 'st_mtime',
                      'size': 'st_size'}
        _stat_pkg = package.stat()
        _stat_pkg = {k: getattr(_stat_pkg, k, None) for k in _stat_attr.keys()}
        _stat_pkg = {k: time.mktime(v.timetuple()) + float(v.microsecond) / 1000000.0 if type(v) is datetime else v for
                     k, v in _stat_pkg.items()}

        _do_load = True
        if not os.path.exists(dest_path):
            os.makedirs(dest_path)
        elif os.path.exists(_dest_file):
            _stat_file = os.stat(_dest_file)
            _do_load = any(_stat_pkg[k] != getattr(_stat_file, v, -999) for k, v in _stat_attr.items())
            if _do_load:
                os.remove(_dest_file)

        if _do_load:
            try:
                # with package.open() as _src:
                _src = requests.get(str(package), auth=package.auth, verify=package.verify, stream=True)
                _src.raise_for_status()

                with open(_dest_file, 'wb+') as _dest:
                    for chunk in _src.iter_content(CHUNK_SIZE):
                        if chunk:  # filter out keep-alive new chunks
                            _dest.write(chunk)
                            _dest.flush()

                _src.close()
                os.utime(_dest_file, (_stat_pkg['ctime'], _stat_pkg['mtime']))

            except Exception as e:
                code = CROSSPM_ERRORCODE_SERVER_CONNECT_ERROR
                msg = 'FAILED to download package {} at url: [{}]'.format(
                    package.name,
                    str(package),
                )
                raise CrosspmException(code, msg) from e

        return _dest_file, _do_load

    def get_package_filename(self, package):
        if isinstance(package, ArtifactoryPath):
            return package.name
        return ''

    def get_package_path(self, package):
        if isinstance(package, ArtifactoryPath):
            return str(package)
        return ''
