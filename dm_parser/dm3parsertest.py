# -*- coding: utf-8 -*-
"""
Created on Sun May 19 07:58:10 2013

@author: matt
"""
from __future__ import absolute_import, print_function, division
from .parse_dm3_grammar import dm3_grammar, dict_to_dm3, dm3_to_dictionary
from file_grammar import ParsedGrammar
import unittest
import StringIO
import array


class dm3test(unittest.TestCase):
    def setUp(self):
        self.g = ParsedGrammar(dm3_grammar, 'header')

    def check(self, data):
        # writes out data into a StringIO, reads it back in again
        # an makes sure they're the same
        s = StringIO.StringIO()
        # dict_to_dm3 is a bit misleadingly named, takes lists too
        self.g.save(s, dict_to_dm3(data))
        s.seek(0)
        ret = dm3_to_dictionary(self.g.open(s))
        self.assertEqual(data, ret)

    def test_list(self):
        self.check([1, 2, 3])

    def test_dict(self):
        self.check({'a': 100, 'b': 200})

    def test_dict2(self):
        self.check({'a': {'b': 100}, 'c': 23.5})

    def test_tagroot_dict_complex(self):
        mydata = {"Bob": 45, "Henry": 67, "Joe": {
                  "hi": [34, 56, 78, 23], "Nope": 56.7,
                  "d": array.array('I', [0] * 32)}}
        self.check(mydata)


if __name__ == "__main__":
    unittest.main()
    # process_all(1)
