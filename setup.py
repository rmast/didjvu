#!/usr/bin/python
# encoding=UTF-8

# Copyright © 2009, 2010, 2011 Jakub Wilk <jwilk@jwilk.net>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 2 dated June, 1991.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.

'''
"*didjvu* uses the `Gamera <http://gamera.informatik.hsnr.de/>`_ framework to
separate foreground/background layers, which it can then encode into a `DjVu
<http://djvu.org/>`_ file."
'''

classifiers = '''
Development Status :: 4 - Beta
Environment :: Console
Intended Audience :: End Users/Desktop
License :: OSI Approved :: GNU General Public License (GPL)
Operating System :: OS Independent
Programming Language :: Python
Programming Language :: Python :: 2
Topic :: Text Processing
Topic :: Multimedia :: Graphics
'''.strip().split('\n')

import glob
import os
import sys

import distutils.core
from distutils.command.build import build as distutils_build
from distutils.command.sdist import sdist as distutils_sdist

from lib.version import __version__

if sys.version_info < (2, 5):
    # Only Python ≥ 2.6 is officially supported, but the software is not completely
    # unusable with Python 2.5:
    raise RuntimeError('didjvu requires Python >= 2.6')
if sys.version_info >= (3, 0):
    raise RuntimeError('didjvu is not compatible with Python 3.X')

class build_doc(distutils_build):

    description = 'build documentation'

    def run(self):
        for xmlname in glob.glob(os.path.join('doc', '*.xml')):
            manname = os.path.splitext(xmlname)[0] + '.1'
            command = [
                'xsltproc', '--nonet',
                '--param', 'man.charmap.use.subset', '0',
                '--param', 'man.font.links', '"I"',
                '--output', 'doc/',
                'http://docbook.sourceforge.net/release/xsl/current/manpages/docbook.xsl',
                xmlname,
            ]
            self.make_file([xmlname], manname, self.spawn, [command])
            if not self.dry_run:
                self.spawn(['./tools/manpage-fixup', manname])

class sdist(distutils_sdist):

    def run(self):
        self.run_command('build_doc')
        return distutils_sdist.run(self)

distutils_build.sub_commands[:0] = [('build_doc', None)]

distutils.core.setup(
    name = 'didjvu',
    version = __version__,
    license = 'GNU GPL 2',
    description = 'DjVu encoder with foreground/background separation',
    long_description = __doc__.strip(),
    classifiers = classifiers,
    url = 'http://jwilk.net/software/didjvu',
    author = 'Jakub Wilk',
    author_email = 'jwilk@jwilk.net',
    packages = ['didjvu'],
    package_dir = dict(didjvu='lib'),
    scripts = ['didjvu'],
    data_files = [('share/man/man1', glob.glob('doc/*.1'))],
    cmdclass = dict(sdist=sdist, build_doc=build_doc),
)

# vim:ts=4 sw=4 et
