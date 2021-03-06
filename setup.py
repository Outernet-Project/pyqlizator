#!/usr/bin/env python

import os
from setuptools import setup


NAME = 'pyqlizator'
VERSION = '0.1'


def read(fname):
    """ Return content of specified file """
    return open(os.path.join(os.path.dirname(__file__), fname)).read()


setup(
    name=NAME,
    version=VERSION,
    license='GPLv3',
    packages=[NAME],
    include_package_data=True,
    long_description=read('README.rst'),
    classifiers=[
        'Development Status :: 3 - Alpha',
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.4',
        'Topic :: Software Development :: Libraries',
    ],
    install_requires=[
        'msgpack-python',
    ],
)
