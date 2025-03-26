#!/usr/bin/env python
# vim: set fileencoding=utf8 shiftwidth=4 tabstop=4 textwidth=80 foldmethod=marker :
# Copyright (c) 2010, Kou Man Tong. All rights reserved.
# Copyright (c) 2015, Ayun Park. All rights reserved.
# For licensing, see LICENSE file included in the package.
import sys

from pip import get_installed_distributions
from setuptools import setup
from setuptools.command.install import install


class NewInstall(install):

    @staticmethod
    def check_pymongo():
        for package in get_installed_distributions():
            if package.project_name == 'pymongo':
                return True
        return False

    def run(self):
        install.run(self)
        if not self.check_pymongo():
            sys.stdout.write('\033[31mCaution! \033[33mbson(pymongo) is already installed.\033[0m\n')


setup(
    name="bson",
    version="0.4.0",
    packages=["bson"],
    install_requires=["pytz>=2010b", "six>=1.9.0"],
    author="Ayun Park",
    author_email="iamparkayun@gmail.com",
    description="BSON codec for Python",
    long_description="""Independent BSON codec for Python that doesn't depend on MongoDB.""",
    platforms="Any",
    license="BSD",
    keywords="BSON codec",
    url="http://github.com/py-bson/bson",
    classifiers=[
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
    ],
    cmdclass={'install': NewInstall}
)
