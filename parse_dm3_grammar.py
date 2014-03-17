# mfm 2014-02-28
# Thinking about doing a non-recursive version to make things simpler
# mfm 2014-02-21 
# moved to  agrammar object now. Can we write too??
# mfm 2013-12-27
#
# Now evaluates only strings or arrays of strings.
# Means we can create reads like >345f.
# also now uses array.read for arrays. These two changes
# make it reasonable for reading large arrays now.
# removed some comments too...

# parse dm3 using a custom grammer style interface.
# we describe entries as name(type) or just simply
# type, which is identical to type(type). Optionally
# a value can be specified for a value, if it doesn't match
# the parser will try the next possibility. If that doesn't
# match, it fails. Different possibilities can be defined by
# having more than one line with the same heading. They will be
# tried in the order specified, so the most general should be last.
# All entries are formatted at run time with the previous read
# names. A special name, 'parent', can be used to access the parent of
# the current location.

# could implement lazy reading at some point, might be fun.
dm3_grammar = """
header:     version(>l)=3, len(>l), endianness(>l)=1, section, end(>l)=0, end2(>l)=0
section:    is_dict(b), open(b), num_tags(>l), data(["named_data"]*num_tags)
named_data: sdtype(b)=20, name_length(>H), name({name_length}s), section
named_data: sdtype(b)=21, name_length(>H), name({name_length}s), dataheader
# struct-specific data entry
dataheader: delim(4s)=%%%%, headerlen(>l), dtype(>l)=15, struct_header, struct_data
# array-specific data entry
dataheader: delim(4s)=%%%%, headerlen(>l), dtype(>l)=20, array_data
# simple data
dataheader: delim(4s)=%%%%, headerlen(>l), dtype(>l), data(simpledata_{dtype})

simpledata_2 = h
simpledata_3 = i
simpledata_4 = H
simpledata_5 = I
simpledata_6 = f
simpledata_7 = d
simpledata_8 = b
simpledata_9 = b
simpledata_10 = b
simpledata_11 = q
simpledata_12 = Q

#structs
struct_header: length(>l)=0, num_fields(>l), types(["struct_dtype"]*num_fields)
struct_data: data([("simpledata_%s" % dtypes.dtype) for dtypes in parent.struct_header.types])
struct_dtype: length(>l)=0, dtype(>l)
 
array_data: arraydtype(>l)=15, struct_header, len(>l), array(["struct_data"]*len)
#general case:
array_data: arraydtype(>l), len(>l), array("{len}"+simpledata_{arraydtype})
"""

import functools
import struct
from collections import defaultdict
import re
from array import array
from logging import root as log


class dottabledict(dict):
    """a dictionary where d[name]==d.name"""
    def __getattr__(self, key):
        return self[key]

    def copy(self):
        return dottabledict(self)

array_compatible_re = re.compile(r"""# any amount of whitepace:
                                     \s*
                                     # optional endianness param, first group:    
                                     ([<>]?)
                                     # required decimal, 2nd group:
                                     (\d+)
                                     # final acceptable character, type, 3rd group:
                                     ([cbBuhHiIlLfd])
                                """, re.VERBOSE)
def get_from_file(f, stype):
    try:
        m = array_compatible_re.match(stype)
        if m:
            m = m.groups()
            # we use the array.array read class
            # only works on files, not file-like!
            # we make an array with the optional endianness and type:
            a = array(m[0]+m[2])
            # then we read from file
            a.fromfile(f, int(m[1]))
            return a
        src = f.read(struct.calcsize(stype))
        assert(len(src) == struct.calcsize(stype))
        d = struct.unpack(stype, src)
    except struct.error:
        return None
    if len(d) == 1:
        return d[0]
    else:
        return d

def write_to_file(f, stype, data):
    log.debug("writing %s as %s", data, stype)
    if isinstance(data, array):
        data = data.tolist()
    elif not isinstance(data, list):
        data = [data]

    f.write(struct.pack(stype, *data))
    return data

class ParsedGrammar(object):
    """
    Encapsulates the methods and data for a parsed grammer.
    When parsing, we will look for attributes in this when resolving names.
    Previous version used either a globals dictionary that was passed to all
    functions, or else the globals() dictionary. Both were unwieldy with the
    latter only effectively allowing one grammar at a time.
    """
    def __init__(self, g, writing=False):
        self.grammar = g
        self.parse(g)
        # we assume if something fails as a NameError or syntax error it
        # will also do so in the future, so we cache the result
        self.writing = writing
        self._types = {}

    def call_option(self, name, data, f):
        """
        Name should be a member of self returning an array of possible
        functions. We call them in order, returning the first one to return
        a non-None value, or None.
        """
        log.debug("Trying %s options", name)
        fpos = f.tell()
        for opt in getattr(self, name):
            r = opt(data, f)
            if r is not None:
                return r
            f.seek(fpos)
    
    def get_string_type_and_evaluate(self, s, env):
        """
        Returns type, obj or [(type, obj), ...]
        Where type is the type of s, and obj is the evaluated object
        type should be either 'atom' or  'struct' but intermediate
        evaluations may use 'evaluable'
        """
        if isinstance(s, list):
            return [self.get_string_type_and_evaluate(x, env) for x in s]
        t = self._types.get(s)
        if t is None:
            if self.is_atom(s):
                self._types[s] = 'atom'
            else:
                try:
                    struct.calcsize(s)
                    self._types[s] = 'struct'  # this is a valid struct string
                except struct.error:
                    self._types[s] = 'evaluable'
            t = self._types[s]

        log.debug("%s has type %s", s, t)
        if t == 'evaluable':
            return self.get_string_type_and_evaluate(
                eval(s, self.__dict__, env), env)
        else:
            return t, s

    def parser(self, data, f, expr, parts):
        """
        The general function that gets called with a line in the grammar
        as an argument.
        f is a file handle used to read types from.
        parts is the list of atoms we expand to.
        Returns a dictionary of name: evaluated expression for each part.

        So For reading, we expect:
        parser({}, f, 'header', ['version(>l)=3', 'len(>l)', 'endianness(>l)=1', 'section'])
        to return (assuming file is corrext)
        {version:3, len:0, endianness:1, section:{...}}
        and for writing
        parser({version:3, len:0, endianness:1, section:{...}}, f, 'header', ['version(>l)=3', 'len(>l)', 'endianness(>l)=1', 'section'])
        would write the same data to the file
        """
        for p in parts:
            log.debug("parsing %s", p)
            # we may have expr=val, so we check that first
            expr = p.split("=", 2)
            expected = None
            if len(expr) == 2:
                expr, expected = expr
            else:
                expr = expr[0]

            # we have, for expr, "name(type)" or just "type" which is
            # equivalent to "type(type)"
            i = expr.find("(")
            if i >= 0:
                # we have a name
                name = expr[:i]
                expr = expr[i+1:-1]
            else:
                name = expr

            # can we _evaluate this?
            # we evaluate with our current return dictionary as locals.
            # this allows a part to reference a previous part as if it was a
            # local note that the evaluation may add more info into locals.
            # We don't want to return this extra info so we use a copy of ret
            # this needs to be dottable though
            expr = expr.format(**data)
            # this will either be tuple ot list of tuples
            types = self.get_string_type_and_evaluate(expr, data)
            is_array = isinstance(types, list)
            if not is_array:
                types = [types]

            if self.writing:
                for i, (atom_type, atom) in enumerate(types):
                    log.debug("Writing %s", data[name])
                    to_write = data[name][i] if is_array else data[name]
                    if atom_type == 'struct':
                        ai = write_to_file(f, atom, to_write)
                    else:
                        to_write['parent'] = data
                        ai = self.call_option(atom, to_write, f)
                        del to_write['parent']
                        if ai is None:
                            return None
            else:
                r = []
                for i, (atom_type, atom) in enumerate(types):
                    if atom_type == 'struct':
                        newdata = get_from_file(f, atom)
                    else:
                        newdata = dottabledict({'parent': data})
                        ai = self.call_option(atom, newdata, f)
                        del newdata['parent']
                        if ai is None:
                            return None
                    r.append(newdata)
                if not is_array:
                    r = r[0]
                data[name] = r

            if expected and str(data[name]) != expected:
                log.debug("%s NOT %s but %s!", name, expected, data[name])
                return None  # incompatible

            # print "%s is %s" % (name, ret[name])
        return data

    def is_atom(self, s):
        return s in self._atoms

    def parse(self, g):
        """ for the description g (see above for info), we find all the
        possibilities and insert into self.
        We also return the processed dictionary"""
        self._literals = []
        self._atoms = []
        ns = defaultdict(list)
        for l in g.splitlines():
            l = l.strip()
            if len(l) == 0 or l[0] == "#":
                continue
            # we have two types of lines:
            # a: b, c, d
            # and
            # a=x
            if l.find("=") != -1 and (
                    l.find(":") > l.find("=") or l.find(":") == -1):
                name, literal = [x.strip() for x in l.split("=")]
                ns[name] = literal
                self._literals.append(name)
            else:
                name, expr = l.split(":")
                # we'll also split up the parts too, and send in to parser func
                parts = [x.strip() for x in expr.split(",")]
                f = functools.partial(self.parser, expr=expr, parts=parts)
                f.__name__ = name
                ns[name].append(f)
                self._atoms.append(name)
        self.__dict__.update(ns)

def dm3_to_dictionary(d):
    """
    Convert the tagged grammer from a dm3 file into a dictionary.
    We convert named data to dictionaries and unnamed to lists.
    """
    def add_to_out(type, data):
        #print type, data
        if type == "section":
            is_dict = data['is_dict']
            ret = {} if is_dict else []
            for item in data['data']:
                if 'section' in item:
                    new_obj = add_to_out('section', item['section'])
                else:
                    new_obj = add_to_out('dataheader', item['dataheader'])
                if is_dict:
                    ret[item['name']] = new_obj
                else:
                    ret.append(new_obj)
            return ret
        elif type == "dataheader":
            if 'struct_data' in data:
                return data['struct_data']['data']
            elif 'array_data' in data:
                return data['array_data']['array']
            else:
                return data['data']

    return add_to_out('section', d['section'])

def parse_dm3_header(file):
    g = ParsedGrammar(dm3_grammar)
    out = g.header[0]({},  file)
    d = dm3_to_dictionary(out)
    return d

if __name__ == '__main__':
    import sys
    import os
    import pprint
    import logging
    logging.basicConfig()
    g = ParsedGrammar(dm3_grammar)
    fname = sys.argv[1] if len(sys.argv) > 1 else "16x2_Ramp_int32.dm3"
    print "opening " + fname
    with open(fname, 'rb') as f:
        out = g.header[0]({},  f)
    g.writing = True
    # log.setLevel(logging.DEBUG)
    with open("out".join(os.path.splitext(fname)), 'wb') as f:
        out2 = g.header[0](out,  f)
    #pprint.pprint(out)
    d = dm3_to_dictionary(out)
    # pprint.pprint(d)
    print "done"
    # would now need to convert to a nicer dict, prefereably one compatible with parse_dm3.

