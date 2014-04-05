# dm3_grammar tester
import unittest
import array
from parse_dm3_grammar import *
from cStringIO import StringIO
import struct
from pprint import pprint
import time
import logging
logging.debug("Hello")

log.setLevel(0)
class dm3GrammarTester(unittest.TestCase):

    def test_struct(self):
        s = StringIO()
        # rest of dataheader
        s.write("%%%%"+struct.pack(">l l", 0, 15))
        # structheader, 3 fields:
        s.write(struct.pack(">l l", 0, 3))
        # structdtype *3 floats (=type6)
        s.write(struct.pack(">l l", 0, 3))
        s.write(struct.pack(">l l", 0, 5))
        s.write(struct.pack(">l l", 0, 2))
        # struct_data
        s.write(struct.pack("< iIh", 43.5, 23.4, 12.7))
        s.seek(0)

        g = ParsedGrammar(dm3_grammar)
        out = dottabledict()
        out.set_file(s)
        ret = g.dataheader[0](out,  s)
        # ret = g.evaluate('dataheader', s)
        pprint(ret)
        time.sleep(0.1)
        retf = ret.flatten()
        print retf
        self.assertDictContainsSubset(
            {'delim': '%%%%',
             'dtype': 15,
             'headerlen': 0,
             'struct_data': {'data': [43, 23, 12]},
             'struct_header': {'length': 0,
                               'num_fields': 3,
                               'types': [{'dtype': 3, 'length': 0},
                                         {'dtype': 5, 'length': 0},
                                         {'dtype': 2, 'length': 0}]}}, retf)

    def x_test_write(self):
        log.setLevel(100)  #disable for reading part...
        s = StringIO()
        # rest of dataheader
        s.write("%%%%"+struct.pack(">l l", 0, 15))
        # structheader, 3 fields:
        s.write(struct.pack(">l l", 0, 3))
        # structdtype *3 floats (=type6)
        s.write(struct.pack(">l l", 0, 3))
        s.write(struct.pack(">l l", 0, 5))
        s.write(struct.pack(">l l", 0, 2))
        # struct_data
        s.write(struct.pack("< iIh", 43.5, 23.4, 12.7))
        s.seek(0)
        g = ParsedGrammar(dm3_grammar)
        ret = g.evaluate('dataheader', s)
        log.setLevel(0)
        gout = ParsedGrammar(dm3_grammar, writing=True)
        sout = StringIO()
        gout.evaluate('dataheader', sout, data=ret)
        sout.seek(0)

        assertEqual(s.read(), sout.read())


if __name__ == "__main__":
    unittest.main()