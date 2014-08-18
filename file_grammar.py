# mfm 2014-05-17
# FileGrammar.py
# Split from parse_dm3_grtammer into its own module

import functools
import struct
import collections
import re
from array import array
import logging
import string
log = logging.root
defaultdict = collections.defaultdict
import re

class DelayedReadDictionary(collections.Mapping):
    """
    A dictionary that stores the file position and data type
    of its elements, and only actually reads them when the item
    is accessed.
    Optionally can be treated as a list, where iter exposes sorted
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
        log.debug("Future access: %s @ %d", key, p)
        self.delayed[key] = (p, stype)
        size = struct.calcsize(stype)
        if self.is_writing:
            if size == 0:
                self.read[key] = None
            else:
                if data is None:
                    data = [0]*size
                    stype = "%sb" % size
                else:
                    self.read[key] = data
                write_to_file(self.f, stype, data)

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
                log.debug("Now writing %s: %s", key, write_data)
                self.read[key] = write_data
            #we have to revert to current pos
            self.f.seek(current_pos)

    def is_pending(self, key):
        """Return true if key hasn't been processed"""
        return key in self.delayed and key not in self.read

    def __setitem__(self, k, v):
        # for writing, we'll write whenever we have the info
        if self.is_writing and k in self.delayed:
            self.do_io(k, v)
        self.read[k] = v

    def __getitem__(self, k):
        # when reading we read just once and assume file is constant
        if not self.is_writing and k not in self.read:
            self.do_io(k)
        # NB this fails regularly, eg when looking for a variable here before
        # globals or if default __contains__ is called
        return self.read[k]


    def __contains__(self, k):
        # default implementation calls getitem and sees if it throws
        # KeyException. We can do better than this
        return k in self.read or k in self.delayed

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
        Convert this and any child mappables to dicts or lists.
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


class dottabledict(DelayedReadDictionary):
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
        self.formatter = string.Formatter()

    def open(self, f):
        self.f = f  # for using f in grammar
        self.writing = False
        parent = dottabledict()
        parent.set_file(f)
        return self.call_option(self.default_type, parent, None)

    def save(self, f, data):
        self.f = f  # for using f in grammar
        self.writing = True
        parent = dottabledict()
        parent.set_file(f)
        return self.call_option(self.default_type, parent, data)

    def call_option(self, atom, io_object, data):
        """
        Name should be a member of self returning an array of possible
        functions. We call them in order, returning the first one to return
        a non-None value, or None.
        """
        log.debug("Calloption: %s", data)
        fpos = io_object.f.tell()
        log.debug("Trying options '%s' @ %s", atom, fpos)
        log.debug('parent is %s' % io_object.keys())
        if not self.writing:
            assert data is None
        # if we are writing, data may be none if it's to be specified later
        # IDeally we should check for this...
        for opt in getattr(self, atom):
            new_io = dottabledict({'parent': io_object})
            new_io.set_file(io_object.f, self.writing)
            r = opt(new_io, data)
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
        io_object is used to map the file into a read/writable dictionary.
        Data is the data to write and should be null for reading
        """
        for p in parts:
            log.debug("parsing %s", p)
            # we may have expr=val, so we check that first
            expr = p.split("=", 2)
            expected = None
            if len(expr) == 2:
                expr, expected = expr
                expected = eval(expected, self.__dict__, io_object)
                log.debug("Expected is %s", expected)
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
            if name not in io_object:
                # can we _evaluate this?
                # we evaluate with our current return dictionary as locals.
                # this allows a part to reference a previous part as if it was a
                # local note that the evaluation may add more info into locals.
                # We don't want to return this extra info so we use a copy of ret
                # this needs to be dottable though
                log.debug("Formatting %s with %s", expr, "")
                # using vformat prevents it from indiscriminately getting all
                # values (as **io_object does)
                # however, get_string_type_and_evaluate copies io_object anyway
                # making this probably irrelevant
                expr = self.formatter.vformat(expr, None, io_object)
                # expr = expr.format(**io_object)
                # this will either be tuple or list of tuples
                types = self.get_string_type_and_evaluate(expr, io_object)
                # we create a list of object, attr names where we
                # setattr(object, name, read_io_object) as we read io_object
                if isinstance(types, list):
                    if self.writing:
                        log.debug("writing list %s, name=%s len=%s",
                                  data[name], name, len(types))
                    get_func = lambda obj, key: obj[name][key]
                    def set_func(obj, key, val):
                        obj[name][key] = val
                    keys = range(len(types))
                    io_object[name] = dottabledict(list_like=True)
                    io_object[name].set_file(io_object.f, self.writing)
                    this_io_object = io_object[name]
                else:
                    # we allow the get_func to return None here is key isn't
                    # present. That way we can write later
                    get_func = lambda obj, key: obj.get(key)
                    def set_func(obj, key, val):
                        obj[key] = val
                    keys = [name]
                    types = [types]
                    this_io_object = io_object

                for k, (atom_type, atom) in zip(keys, types):
                    source_data = get_func(data, k) if self.writing else None
                    if atom_type == 'struct':
                        this_io_object.set_key_here(k, atom, source_data)
                    else:
                        newio_object = self.call_option(atom, io_object, source_data)
                        if newio_object is None:
                            return None
                        this_io_object[k] = newio_object

            if expected is not None:
                if self.writing and io_object.is_pending(name):
                    # we set the name to expected
                    log.debug("Setting %s to %s", name, expected)
                    io_object[name] = expected
                elif io_object[name] != expected:
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
        # replace newline, whitespace with '' to allow splitting grammar
        # into multiple lines
        g = re.sub('\n[\t\f\v ]+', '', g)
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

