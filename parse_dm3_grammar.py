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
header:     version(>l)=3, len(>l), endianness(>l)=1, section
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
        self.failed_eval_cache = {}
        self.writing = writing
        self.incompatible_stypes = {}

    def transfer(self, dic, name, stype, f):
        """
        Transfer an item between the dict and the file.
        If writing, writes dic[name] into file using stype.
        If reading, sets dic[name] to stype as read from file.
        """
        if stype in self.incompatible_stypes:
            return None

        if self.writing:
            log.debug("writing %s as %s", dic[name], stype)
            f.write(struct.pack(stype, dic[name]))
        else:
            src = get_from_file(f, stype)
            if src is None:
                log.debug("Adding %s to incompatible struct types", stype)
                self.incompatible_stypes[stype] = True
                return None
            dic[name] = src
        return dic[name]
            


    def evaluate(self, func, f, data=None):
        if self.writing:
            assert data is not None
        data = data or {}
        return self._evaluate(func, data, "", f)
    
    def _evaluate(self, func, lns, name, f):
        """
        Take a func and uses the lns as a local dictionary. self.__dict__ is
        used as a dictionary containing functions that func can evaluate to.
        Func can be three types here, a string, which we simply eval() and then
        call this again, a function, which we call with a new namespace,
        or a list, which we again call this for every one.
        We return the evaluated expression, or None if no suitable rules were
        found
        """
        log.debug("Trying %s: %s", func.__name__ if hasattr(func, '__name__') else func, type(func))
        if isinstance(func, str):
            if func in self.failed_eval_cache:
                return None
            # we see if this exists in our namespace first
            if hasattr(self, func):
                # no point calling eval here, we know exactly what it will eval to!
                pos = f.tell()
                for subf in getattr(self, func):
                    ret = self._evaluate(subf, lns, name, f)
                    if ret is not None:
                        return ret
                    f.seek(pos)  # rewind
                else:
                    log.info("No compatible '%s' found! (from %s possibilities)", 
                        func, len(getattr(self, func)))
                    return None
            else:
                # next we try to get from file
                t = self.transfer(lns, name, func, f)
                if t is not None:
                    log.debug("Found struct string %s=%s", func, t)
                    return t
                try:
                    return self._evaluate(eval(func, self.__dict__, lns.copy()), lns, name, f)
                except (SyntaxError, NameError) as e:
                    log.info("_evaluate failed", exc_info=1)
                    self.failed_eval_cache[func] = True
                    return None

        if callable(func):
            if not self.writing:
                lns[name] = dottabledict()
            lns[name]['parent'] = lns
            ret = func(lns[name], f)
            del lns[name]['parent']
            if ret is None:
                del lns[name]  # no good
                log.debug("function %s failed for %s", func, name)
                return None
            return ret
        else:
            ret = []
            for fu in func:
                newval = self._evaluate(fu, lns, name, f)
                if newval is None:
                    log.debug("function %s (of %s) failed for %s", func, len(fu), name)
                    return None
                ret.append(newval)
            lns[name] = ret
            return ret
        log.error("%s not evluable!",  func)
    

    def parser(self, data,  f, expr, parts):
        """
        The general function that gets called with a line in the grammar
        as an argument.
        Evaluates the expression expr in the namespace ns.
        f is a file handle used to read types from.
        lns and gns are the local and global namespaces respectively.
        parts is the list of atoms we expand to.
        Returns a dictionary of name: evaluated expression for each part."""
        for p in parts:
            # first, we format with the current 
            p = p.format(**data)
            #p = p.format(**gns)
            log.debug("parsing %s", p)
            # we may have expr=val, so we check that first
            expr = p.split("=", 2)
            expected = None
            if len(expr) == 2:
                expr, expected = expr
            else:
                expr = expr[0]

            # we have, for expr, "name(type)" or just "type" which is equivalent to
            # "type(type)" 
            i = expr.find("(")
            if i >= 0:
                # we have a name
                name = expr[:i]
                expr = expr[i+1:-1]
            else:
                name = expr

            # can we _evaluate this?
            # we evaluate with our current return dictionary as locals.
            # this allows a part to reference a previous part as if it was a local
            # note that the evaluation may add more info into locals. We don't want
            # to return this extra info so we use a copy of ret
            # this needs to be dottable though
            new_ret = self._evaluate(expr, data, name, f)
            if new_ret is None:
                return None

            if expected and str(new_ret) != expected:
                log.debug("%s NOT %s but %s!", name, expected, new_ret)
                return None  # incompatible

            # print "%s is %s" % (name, ret[name])
        return data


    def parse(self, g):
        """ for the description g (see above for info), we find all the
        possibilities and insert into self.
        We also return the processed dictionary"""
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
                name, literal = l.split("=")
                ns[name.strip()] = literal.strip()
            else:
                name, expr = l.split(":")
                # we'll also split up the parts too, and send in to parser func
                parts = [x.strip() for x in expr.split(",")]
                f = functools.partial(self.parser, expr=expr, parts=parts)
                f.__name__ = name
                ns[name].append(f)
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
    out = g.evaluate('header', file)
    d = dm3_to_dictionary(out)
    return d

if __name__ == '__main__':
    import sys
    import pprint
    g = ParsedGrammar(dm3_grammar)
    fname = sys.argv[1] if len(sys.argv) > 1 else "16x2_Ramp_int32.dm3"
    print "opening " + fname
    with open(fname, 'rb') as f:
        out = g.evaluate('header',  f)
    pprint.pprint(out)
    d = dm3_to_dictionary(out)
    # pprint.pprint(d)
    print "done"
    # would now need to convert to a nicer dict, prefereably one compatible with parse_dm3.

