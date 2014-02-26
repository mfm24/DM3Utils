# -*- coding: utf-8 -*-
"""
Created on Sun May 19 07:58:10 2013

@author: matt
"""

from ParseDM3File import *
import unittest
import StringIO
import numpy as np


class dm3test(unittest.TestCase):
    def check(self, data, func, _assert=True):
        # we confirm that reading a written element returns the same value
        s = StringIO.StringIO()
        header = func(s, outdata=data)
        s.seek(0)
        if header is not None:
            r, hy = func(s)
        else:
            r = func(s)
        if _assert:
            self.assertEqual(r, data)
        return r

    def test_dm_read_struct_types(self):
        s = StringIO.StringIO()
        types = [2, 2, 2]
        dm_read_struct_types(s, outtypes=types)
        s.seek(0)
        in_types, headerlen = dm_read_struct_types(s)
        self.assertEqual(in_types, types)

    def test_simpledata(self):
        self.check(45, dm_types[get_dmtype_for_name('long')])
        self.check(2**30, dm_types[get_dmtype_for_name('ulong')])
        self.check(34.56, dm_types[get_dmtype_for_name('double')])

    def test_read_string(self):
        data = "MyString"
        ret = self.check(data, dm_types[get_dmtype_for_name('array')], False)
        for d, r in zip(data, ret):
            self.assertEqual(int(ord(d)), int(r))

    def test_array_simple(self):
        dat = array.array('b', [0]*256)
        self.check(dat, dm_types[get_dmtype_for_name('array')])

    def test_array_struct(self):
        dat = structarray(['h', 'h', 'h'])
        dat.raw_data = '0x00'*(3*20)
        self.check(dat, dm_types[get_dmtype_for_name('array')])

    def test_tagdata(self):
        for d in [45, 2**31, 34.56, array.array('b', [0]*256)]:
            self.check(d, parse_dm_tag_data)

    def test_tagroot_dict(self):
        mydata = {}
        self.check(mydata, parse_dm_tag_root)
        mydata = {"Bob": 45, "Henry": 67, "Joe": 56}
        self.check(mydata, parse_dm_tag_root)

    def test_tagroot_dict_complex(self):
        mydata = {"Bob": 45, "Henry": 67, "Joe": {
                  "hi": [34, 56, 78, 23], "Nope": 56.7, "d": array.array('L', [0] * 32)}}
        self.check(mydata, parse_dm_tag_root)

    def test_tagroot_list(self):
        # note any strings here get converted to 'H' arrays!
        mydata = []
        self.check(mydata, parse_dm_tag_root)
        mydata = [45,  67,  56]
        self.check(mydata, parse_dm_tag_root)

    def test_struct(self):
        # note any strings here get converted to 'H' arrays!
        mydata = tuple()
        f = dm_types[get_dmtype_for_name('struct')]
        self.check(mydata, f)
        mydata = (3, 4, 56.7)
        self.check(mydata, f)

    def test_image(self):
        im = array.array('h')
        im.fromstring(np.random.random(16))
        im_tag = {"Data": im,
                  "Dimensions": [23, 45]}
        s = StringIO.StringIO()
        parse_dm_tag_root(s, outdata=im_tag)
        s.seek(0)
        ret = parse_dm_tag_root(s)
        self.assertEqual(im_tag["Data"], ret["Data"])
        self.assertEqual(im_tag["Dimensions"], ret["Dimensions"])
        self.assert_((im_tag["Data"] == ret["Data"]))

# some functions for processing multiple files.
# useful for testing reading and writing a large number of files.
import os


def process_dm3(path, mode):
    opath = path + ".out.dm3"
    data = odata = None
    if mode == 0 or mode == 1:  # just open source
        # path=opath
        with open(path, 'rb') as f:
            data = parse_dm_header(f)
    if mode == 1:  # open source, write to out
        with open(opath, 'wb') as f:
            parse_dm_header(f, outdata=data)
    elif mode == 2:  # open both
        with open(path, 'rb') as f:
            data = parse_dm_header(f)
        with open(opath, 'rb') as f:
            odata = parse_dm_header(f)
        # this ensures keys in root only are the same
        assert(sorted(odata) == sorted(data))
    return data, odata


def process_all(mode):
    for f in [x for x in os.listdir(".")
              if x.endswith(".dm3")
              if not x.endswith("out.dm3")]:
        print "reading", f, "..."
        data, odata = process_dm3(f, mode)

if __name__ == "__main__":
    unittest.main()
    # process_all(1)
