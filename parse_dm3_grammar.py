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
#
# additionally variables can be defined starting with _. No atoms should
# therefore begin with _ as they won't be looked up
dm3_grammar = """
header:     version(>l)=3, len(>l), _pos=f.tell(), endianness(>l)=1, section, len=f.tell()-_pos
section:    is_dict(b), open(b), num_tags(>l), data(["named_data"]*num_tags)
named_data: sdtype(b)=20, name_length(>H), name({name_length}s), section
named_data: sdtype(b)=21, name_length(>H), name({name_length}s), dataheader
# struct-specific data entry
dataheader: delim(4s)="%%%%", headerlen(>l),  _pos=f.tell(), dtype(>l)=15, struct_header, headerlen=(f.tell()-_pos)/4, struct_data
# array-specific data entry
dataheader: delim(4s)="%%%%", headerlen(>l), _pos=f.tell(), dtype(>l)=20, array_data, headerlen=(array_data._end-_pos)/4,
# simple data
dataheader: delim(4s)="%%%%", headerlen(>l), _pos=f.tell(),  dtype(>l), headerlen=(f.tell()-_pos)/4, data(simpledata_{dtype})

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

array_data: arraydtype(>l)=15, struct_header, len(>l), _end=f.tell(), array(["struct_data"]*len)
#general case:
array_data: arraydtype(>l), len(>l), _end=f.tell(), array("{len}"+simpledata_{arraydtype})
"""

import functools
import struct
from collections import defaultdict
import collections
import re
from array import array
import logging
log = logging.root

class DelayedReadDictionary(collections.Mapping):
    """
    A dictionary that stores the file position and data type
    of its elements, and only actually reads them when the item
    is accessed.
    Optionally can be treated by a list, where iter exposes sorted
    values rather than keys.
    """
    def __init__(self, items=None, list_like=False):
        self.delayed = {}
        self.read = {}
        # dict.__init__(*args) doesn't call update for some reason
        if items:
            self.read.update(items)
        self.list_like=list_like
        self.is_writing = False

    def set_file(self, f, is_writing=False):
        self.f = f
        # delayed is a key: (fpos, type) dictionary
        self.is_writing = is_writing
        assert 'is_writing' in self.__dict__
        self.delayed = {}

    def set_key_here(self, key, stype, data=None):
        """
        Sets an entry in the delayed read list. This will be read from
        the file in getitem if needed later
        If writing, data or an empty value will be written here.
        Later calls to setitem will write to this position
        """
        p = self.f.tell()
        log.debug("Future read: %s @ %d", key, p)
        self.delayed[key] = (p, stype)
        size = struct.calcsize(stype)
        if self.is_writing:
            if data is None:
                data = [0]*size
                stype = "%sb" % size
            else:
                self.read[key] = data
            write_to_file(f, stype, data)

        self.f.seek(p + size)

    def do_io(self, key, write_data=None):
        if key in self.delayed:
            current_pos = self.f.tell()
            pos, stype = self.delayed[key]
            self.f.seek(pos)
            if not self.is_writing:
                self.read[key] =  get_from_file(self.f, stype)
                log.debug("Now reading %s: %s", key, self.read[key])
            else:
                write_to_file(self.f, stype, write_data)
                log.debug("Now writing %s: %s", key, v)
                self.read[key] = v
            #we have to revert to current pos
            self.f.seek(current_pos)

    def __setitem__(self, k, v):
        # for writing, we'll write whenever we have the info
        if self.is_writing and k in self.delayed:
            self.do_io(k, v)
        self.read[k] = v

    def __getitem__(self, k):
        # when reading we read just once and assume file is constant
        assert 'is_writing' in self.__dict__
        if not self.is_writing and k not in self.read:
            self.do_io(k)
        return self.read[k]

    def __delitem__(self, k):
        if k in self.read:
            del self.read[k]
        if k in self.delayed:
            del self.delayed[k]

    # need __iter__, __getitem__ and __len__ to be a mapping we can pass with **
    def __iter__(self):
        items = set(self.delayed.keys() + self.read.keys())
        if self.list_like:
            items = [self[k] for k in sorted(items)]
        log.debug("Iter exposes %s", items)
        for k in items:
            yield k

    def __len__(self):
        return len(set(self.delayed.keys() + self.read.keys()))

    def to_std_type(self):
        """
        Convert this and aay child mappables to dicts.
        Additionally, DelayedReadDictionary with like_list are converted
        to lists
        """
        if self.list_like:
            ret = []
            for i in self:
                if hasattr(i, "to_std_type"):
                    ret.append(i.to_std_type())
                else:
                    ret.append(i)
        else:
            ret = {}
            for i in self:
                if hasattr(self[i], "to_std_type"):
                    ret[i] = self[i].to_std_type()
                else:
                    ret[i] = self[i]
        return ret


dottabledict_base = DelayedReadDictionary
#dottabledict_base = dict

class dottabledict(dottabledict_base):
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
    def __init__(self, g, default_type, writing=False):
        self.grammar = g
        self.parse(g)
        # we assume if something fails as a NameError or syntax error it
        # will also do so in the future, so we cache the result
        self.writing = writing
        self._types = {}
        self.default_type = default_type

    def open(self, f):
        self.f = f  # for using f in grammar
        parent = dottabledict()
        parent.set_file(f)
        return self.call_option(self.default_type, parent, None)

    def call_option(self, atom, io_object, data):
        """
        Name should be a member of self returning an array of possible
        functions. We call them in order, returning the first one to return
        a non-None value, or None.
        """
        fpos = io_object.f.tell()
        log.debug("Trying options '%s' @ %s", atom, fpos)
        if not self.writing:
            assert data is None
        for opt in getattr(self, atom):
            new_io = dottabledict({'parent': io_object})
            new_io.set_file(io_object.f, self.writing)
            r = opt(new_io, None)
            if r is not None:
                del new_io['parent']
                return r
            log.debug('Option %s failed, rewinding to %s', opt, fpos)
            io_object.f.seek(fpos)
        log.debug("No valid options '%s' @ %s!", atom, fpos)

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
            log.debug("evaluating %s", s)
            # evaluating may create variables that we don't want put in env
            # yet at the same time we need both env (for local information)
            # and self.__dict__ (for evaluating to atoms).
            # let's send in a copy of env
            return self.get_string_type_and_evaluate(
                eval(s, self.__dict__, env.copy()), env)
        else:
            return t, s

    def parser(self, io_object, data, expr, parts):
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
        would write the same io_object to the file
        """
        for p in parts:
            log.debug("parsing %s", p)
            # we may have expr=val, so we check that first
            expr = p.split("=", 2)
            expected = None
            if len(expr) == 2:
                expr, expected = expr
                expected = eval(expected, self.__dict__, io_object)
                assert expected is not None
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

            # if name begins with '_', it's a variable. It gets set by its
            # expected value and can never be an atom or need formatting
            if name.startswith('_'):
                # would be nice to keep this separate from our explicitly
                # read / written io_object. Maybe we could ignore this when
                # converting to dict?
                io_object[name] = expected
                log.debug("setting variable '%s' to %s", name, expected)
                continue

            # If name exists already in io_object, we assume this is a check.
            # we want to be able to say
            # atom: len(>l), len=4
            # and have the second statement realise it refers to an existing
            # variable and check it. When writing we'll write this. The main
            # reason for this is to allow length paramaters:
            # atom: len(>l), ..., len=f.tell()-len.pos
            # maybe...
            # this doesn't work - we're reusing our newio_object array in call_opt
            # even when we fail, I think we should start being stricter about
            # our dictionaries: we have env, in (if writing) and out
            # and we shouldn't try to get away with just one. Would also be
            # nice to standardise on reading returning and writing taking
            # input only?
            if name in io_object:
                if io_object[name] != expected:
                    print "'%s'=%s IS NOT %s" % (name, io_object[name], expected)
                continue
            # can we _evaluate this?
            # we evaluate with our current return dictionary as locals.
            # this allows a part to reference a previous part as if it was a
            # local note that the evaluation may add more info into locals.
            # We don't want to return this extra info so we use a copy of ret
            # this needs to be dottable though
            expr = expr.format(**io_object)
            # this will either be tuple or list of tuples
            types = self.get_string_type_and_evaluate(expr, io_object)
            # we create a list of object, attr names where we
            # setattr(object, name, read_io_object) as we read io_object
            if isinstance(types, list):
                if not self.writing:
                    io_object[name] = dottabledict(list_like=True)
                    io_object[name].set_file(io_object.f)
                keys = range(len(types))
                write_object = io_object[name]
            else:
                write_object = io_object
                keys = [name]
                types = [types]

            if self.writing:
                for k, (atom_type, atom) in zip(keys, types):
                    log.debug("Writing %s", io_object[name])
                    to_write = write_object.__getitem__(k)
                    if atom_type == 'struct':
                        ai = write_to_file(io_object.f, atom, to_write)
                    else:
                        ai = self.call_option(atom, io_object, to_write, io_object.f)
                        if ai is None:
                            return None
            else:
                for k, (atom_type, atom) in zip(keys, types):
                    if atom_type == 'struct':
                        #newio_object = get_from_file(f, atom)
                        write_object.set_key_here(k, atom)
                    else:
                        newio_object = self.call_option(atom, io_object, None)
                        if newio_object is None:
                            return None
                        write_object.__setitem__(k, newio_object)

            if expected:
                if io_object[name] != expected:
                    log.debug("%s NOT %s but %s!", name, expected, io_object[name])
                    return None  # incompatible
                else:
                    log.debug("%s IS %s!", name, expected)

            # print "%s is %s" % (name, ret[name])
        assert io_object is not None
        return io_object

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
    g = ParsedGrammar(dm3_grammar, 'header')
    out = g.open(file)
    d = dm3_to_dictionary(out)
    return d

if __name__ == '__main__':
    import sys
    import os
    import pprint
    logging.basicConfig()
    log.setLevel(logging.DEBUG)
    g = ParsedGrammar(dm3_grammar, 'header')
    fname = sys.argv[1] if len(sys.argv) > 1 else "16x2_Ramp_int32.dm3"
    print "opening " + fname

    with open(fname, 'rb') as nosingleletter_f:
        out = g.open(nosingleletter_f)
        # any potential reads have to be done with the file still open
        d = dm3_to_dictionary(out)
    g.writing = True
    # log.setLevel(logging.DEBUG)
    write_also = False
    if write_also:
        with open("out".join(os.path.splitext(fname)), 'wb') as nosingleletter_f:
            out2 = g.header[0](out,  nosingleletter_f)
    #pprint.pprint(out)

    # pprint.pprint(d)
    print "done"
    # would now need to convert to a nicer dict, prefereably one compatible with parse_dm3.

