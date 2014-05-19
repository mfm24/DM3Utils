import unittest
from file_grammar import *
from cStringIO import StringIO
import struct
import logging


class FileGrammarTester(unittest.TestCase):
    def test_grammar1(self):
        # we test a simple grammar consisting of a length>0, and a string
        # that long and another item, or else a zero:
        desc = ("atom: len(<l)=0\n"
                "atom: len(<l), string({len}s), atom")
        g = ParsedGrammar(desc, 'atom')
        def add_string(s, f):
            if s:
                f.write(struct.pack('<l{len}s'.format(len=len(s)), len(s), s))
            else:
                # terminating case
                f.write(struct.pack('<l', 0))
        sin = StringIO()
        add_string("hithere", sin)
        add_string("bob", sin)
        add_string("alice & jeff", sin)
        add_string(None, sin)
        sin.seek(0)
        parsed = g.open(sin)
        self.assertEqual(parsed.string, 'hithere')
        self.assertEqual(parsed.len, len('hithere'))
        #self.assertEqual(parsed)

if __name__ == '__main__':
    # logging.basicConfig()
    # logging.root.setLevel(logging.DEBUG)
    unittest.main()

