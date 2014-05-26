import unittest
from file_grammar import *
from cStringIO import StringIO
import struct
import logging


class FileGrammarTester(unittest.TestCase):
    def setUp(self):
        # we test a simple grammar consisting of a length>0, and a string
        # that long and another item, or else a zero:
        self.desc = ("atom: len(<l)=0\n"
                "atom: len(<l), string({len}s), atom")
        self.g = ParsedGrammar(self.desc, 'atom')

    @staticmethod
    def add_string(s, f):
        """ Add the string s to the file f directly, not using grammar"""
        if s:
            f.write(struct.pack('<l{len}s'.format(len=len(s)), len(s), s))
        else:
            # terminating case
            f.write(struct.pack('<l', 0))

    def data_to_iter(self, atom):
        """Convert data from grammar to an iteratro over the strings"""
        while atom.len > 0:
            self.assertEqual(len(atom.string), atom.len)
            yield atom.string
            atom = atom.atom

    def to_data(self, strings):
        """Convert the list strings to a dictionary compatible with our grammar"""
        if len(strings) > 0:
            s, ss = strings[0], strings[1:]
            return dict(len=len(s), string=s, atom=self.to_data(ss))
        else:
            return dict(len=0)

    def test_grammar1(self):
        sin = StringIO()
        self.add_string("hithere", sin)
        self.add_string("bob", sin)
        self.add_string("alice & jeff", sin)
        self.add_string(None, sin)
        sin.seek(0)
        parsed = self.g.open(sin)


        self.assertEqual(parsed.string, 'hithere')
        self.assertEqual(parsed.len, len('hithere'))
        self.assertEqual(list(self.data_to_iter(parsed)), ['hithere', 'bob', 'alice & jeff'])
        #self.assertEqual(parsed)

    def test_grammar2(self):
        """Test writing the grammar"""
        sin = StringIO()
        strings = ["Hello", "Bob", "A long string", "f", "g"]
        data = self.to_data(strings)
        self.g.save(sin, data)
        sin.seek(0)
        parsed = self.g.open(sin)
        self.assertEqual(parsed, data)

    def test_grammar3(self):
        """Test writing is identical to self.add_string"""
        strings = ["Hello", "Bob", "A long string", "f", "g"]
        sin = StringIO()
        self.g.save(sin, self.to_data(strings))

        sin2 = StringIO()
        for s in strings:
            self.add_string(s, sin2)
        self.add_string(None, sin2)

        sin.seek(0)
        sin2.seek(0)
        self.assertEqual(sin.read(), sin2.read())


if __name__ == '__main__':
    # logging.basicConfig()
    # logging.root.setLevel(logging.DEBUG)
    unittest.main()

