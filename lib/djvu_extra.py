# encoding=UTF-8

# Copyright © 2009, 2010 Jakub Wilk <jwilk@jwilk.net>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 2 dated June, 1991.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.

'''Wrappers for the DjVuLibre utilities'''

import os
import re
import shutil

from . import ipc
from . import temporary

DPI_MIN = 72
DPI_DEFAULT = 300
DPI_MAX = 6000

LOSS_LEVEL_MIN = 0
LOSS_LEVEL_DEFAULT = 100
LOSS_LEVEL_MAX = 200

SUBSAMPLE_MIN = 1
SUBSAMPLE_DEFAULT = 3
SUBSAMPLE_MAX = 12

IW44_SLICES_DEFAULT = (74, 89, 99)

CRCB_FULL = 3
CRCB_NORMAL = 2
CRCB_HALF = 1
CRCB_NONE = 0

def bitonal_to_djvu(image, dpi=300, loss_level=0):
    pbm_file = temporary.file(suffix='.pbm')
    image.save(pbm_file.name)
    djvu_file = temporary.file(suffix='.djvu', mode='r+b')
    args = ['cjb2', '-losslevel', str(loss_level), pbm_file.name, djvu_file.name]
    return ipc.Proxy(djvu_file, ipc.Subprocess(args).wait, [pbm_file])

_crcb_map = {
    CRCB_FULL: 'full',
    CRCB_NORMAL: 'normal',
    CRCB_HALF: 'half',
    CRCB_NONE: 'none',
}

def photo_to_djvu(image, dpi=100, slices=IW44_SLICES_DEFAULT, gamma=2.2, mask_image=None, crcb=CRCB_NORMAL):
    ppm_file = temporary.file(suffix='.ppm')
    temporaries = [ppm_file]
    image.save(ppm_file.name)
    djvu_file = temporary.file(suffix='.djvu', mode='r+b')
    args = [
        'c44',
        '-dpi', str(dpi),
        '-slice', ','.join(map(str, slices)),
        '-gamma', '%.1f' % gamma,
        '-crcb%s' % _crcb_map[crcb],
    ]
    if mask_image is not None:
        pbm_file = temporary.file(suffix='.pbm')
        mask_image.save(pbm_file.name)
        args += ['-mask', pbm_file.name]
        temporaries += [pbm_file]
    args += [ppm_file.name, djvu_file.name]
    return ipc.Proxy(djvu_file, ipc.Subprocess(args).wait, temporaries)

def djvu_to_iw44(djvu_file):
    iw44_file = temporary.file(suffix='.iw44')
    args = ['djvuextract', djvu_file.name, 'BG44=%s' % iw44_file.name]
    return ipc.Proxy(iw44_file, ipc.Subprocess(args).wait, [djvu_file])

def _int_or_none(x):
    if x is None:
        return
    if isinstance(x, int):
        return x
    raise ValueError

def _sjbz_first(key):
    # djvuextract expects Sjbz=… before PPM=…
    return key[0] != 'sjbz'

class Multichunk(object):

    _chunk_names = 'Sjbz Smmr BG44 BGjp BG2k FGbz FG44 FGjp FG2k INCL Djbz'
    _chunk_names = dict((x.lower(), x) for x in _chunk_names.split())
    _info_re = re.compile(' ([0-9]+)x([0-9]+),.* ([0-9]+) dpi,').search

    def __init__(self, width=None, height=None, dpi=None, **chunks):
        self.width = _int_or_none(width)
        self.height = _int_or_none(height)
        self.dpi = _int_or_none(dpi)
        self._chunks = {}
        for (k, v) in chunks.iteritems():
            self.set(k, v)

    @classmethod
    def from_file(cls, djvu_file):
        self = cls()
        args = ['djvudump', djvu_file.name]
        dump = Subprocess(args, stdout=subprocess.PIPE)
        width = height = dpi = None
        keys = set()
        try:
            header = dump.stdout.readline()
            if not header.startswith('  FORM:DJVU '):
                raise ValueError
            for line in dump.stdout:
                if line[:4] == '    ' and line[8:9] == ' ':
                    key = line[4:8]
                    if key == 'INFO':
                        m = cls._info_re(line[8:])
                        self.width, self.height, self.dpi = m.groups()
                    else:
                        keys.add(key)
                else:
                    ValueError
        finally:
            dump.wait()
        args = ['djvuextract', djvu_file.name]
        chunk_files = {}
        for key in keys:
            chunk_file = temporary.file(suffix='.%s-chunk' % key.lower())
            args += ['%s=%s' % (key, chunk_file.name)]
            chunk_files[key] = chunk_file
        djvuextract = Subprocess(args, stderr=open(os.devnull, 'w'))
        for key in keys:
            self.set(key, Proxy(chunk_files[key], djvuextract.wait, [djvu_file]))
        return self

    def set(self, key, value):
        if key == 'image':
            ppm_file = temporary.file(prefix='didjvu', suffix='.ppm')
            value.save(ppm_file.name)
            key = 'PPM'
            value = ppm_file
        else:
            key = key.lower()
            if key not in self._chunk_names:
                raise ValueError
        self._chunks[key] = value

    def get(self, key):
        key = key.lower()
        return self._chunks[key]

    def save(self):
        if self.width is None:
            raise ValueError
        if self.height is None:
            raise ValueError
        if self.dpi is None:
            raise ValueError
        if len(self._chunks) == 0:
            raise ValueError
        args = ['djvumake', None, 'INFO=%d,%d,%d' % (self.width, self.height, self.dpi)]
        for key, value in sorted(self._chunks.iteritems(), key=_sjbz_first):
            try:
                key = self._chunk_names[key]
            except KeyError:
                pass
            if not isinstance(value, str):
                value = value.name
            if key == 'BG44':
                value += ':999'
            args += ['%s=%s' % (key, value)]
        tmpdir = temporary.directory()
        try:
            djvu_filename = args[1] = os.path.join(tmpdir, 'result.djvu')
            ipc.Subprocess(args).wait()
            djvu_new_filename = temporary.name(suffix='.djvu')
            os.link(djvu_filename, djvu_new_filename)
            return temporary.wrapper(file(djvu_new_filename, mode='r+b'), djvu_new_filename)
        finally:
            shutil.rmtree(tmpdir)

def bundle_djvu(*component_filenames):
    djvu_file = temporary.file(suffix='.djvu')
    args = ['djvm', '-c', djvu_file.name]
    args += component_filenames
    return ipc.Proxy(djvu_file, ipc.Subprocess(args).wait, None)

__all__ = [
    'bitonal_to_djvu', 'photo_to_djvu', 'djvu_to_iw44',
    'Multichunk',
    'DEBUG',
    'DPI_MIN', 'DPI_DEFAULT', 'DPI_MAX',
    'LOSS_LEVEL_MIN', 'LOSS_LEVEL_DEFAULT', 'LOSS_LEVEL_MAX',
    'SUBSAMPLE_MIN', 'SUBSAMPLE_DEFAULT', 'SUBSAMPLE_MAX',
    'IW44_SLICES_DEFAULT',
    'CRCB_FULL', 'CRCB_NORMAL', 'CRCB_HALF', 'CRCB_NONE',
]

# vim:ts=4 sw=4 et
