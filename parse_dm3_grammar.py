# parse_dm3_grammar.py
# contains a gramar definition for a dm3 files and helper functions for converting
# to and from dictionaries, and extracting images
import logging
from array import array
from file_grammar import ParsedGrammar

general_grammar = """
header:     version(>l)=__version__, len(__len_type__), endianness(>l)=1, _pos=f.tell(), section, 
            len=f.tell()-_pos-__header_offset__, zero_pad_0(>l)=0, zero_pad_1(>l)=0

section:    is_dict(b), open(b), num_tags(__len_type__), data(["named_data"]*num_tags)

named_data: sdtype(b)=20, name_length(>H), name({name_length}s), 
            __named_data_pre__ section __named_data_post__

named_data: sdtype(b)=20, name_length(>H), name({name_length}s), 
            __named_data_pre__ dataheader __named_data_post__

# struct-specific data entry
dataheader: delim(4s)="%%%%", headerlen(__len_type__), _pos=f.tell(),
            dtype(__len_type__)=15, struct_header, 
            headerlen=(f.tell()-_pos)/__len_size__, struct_data

# array-specific data entry
dataheader: delim(4s)="%%%%", headerlen(__len_type__), _pos=f.tell(),
            dtype(__len_type__)=20, array_data,
            headerlen=(array_data._end-_pos)/__len_size__

# simple data
dataheader: delim(4s)="%%%%", headerlen(__len_type__), _pos=f.tell(), 
            dtype(__len_type__), 
            headerlen=(f.tell()-_pos)/__len_size__, data(simpledata_{dtype})

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
struct_header: length(__len_type__)=0, num_fields(__len_type__),
               types(["struct_dtype"]*num_fields)

struct_data: data([("simpledata_%s" % dtypes.dtype) for dtypes in parent.struct_header.types])

struct_dtype: length(__len_type__)=0, dtype(__len_type__)

array_data: arraydtype(__len_type__)=15, struct_header, len(__len_type__),
            _end=f.tell(), array(["struct_data"]*len)

#general case:
array_data: arraydtype(__len_type__), len(__len_type__),
            _end=f.tell(), array("{len}"+simpledata_{arraydtype})
"""

# dm3 vs dm4 differences:
# version 3 -> 4
# len_type l -> Q
# Slight difference in the header size calculation ('header_offset')
# (I think v3 is including the 'endianness' field and v4 isn't)
# v4 has size fields for the named_data element
dm3_grammer_defs = { 'version': 3,
                     'len_type': '>l',
                     'len_size': 4,
                     'header_offset': 4,
                     'named_data_pre': '',
                     'named_data_post': '',
                     }

dm4_grammer_defs = { 'version': 4,
                     'len_type': '>Q',
                     'len_size': 8,
                     'header_offset': 0,
                     'named_data_pre': 'datalen(>Q), _pos=f.tell(), ',
                     'named_data_post': ', datalen=f.tell()-_pos',
                     }

def replace_map(s, m):
    for k, v in m.items():
        s = s.replace('__%s__' % k, str(v))
    return s

dm3_grammar = replace_map(general_grammar, dm3_grammer_defs)
dm4_grammar = replace_map(general_grammar, dm4_grammer_defs)

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
                return tuple(data['struct_data']['data'])
            elif 'array_data' in data:
                return data['array_data']['array']
            else:
                return data['data']

    return add_to_out('section', d['section'])

def dict_to_dm3(d):
    """
    Convert a dictionary (like the one returned from dm3_to_dictionary) into
    a structure suitable for writing with the dm3 grammar.
    """
    # we basically have four mappings:
    # 1. dict or list to section
    # 2. simple data to dataheader
    # 3. array.array to array dataheader
    # 4. tuple to struct dataheader
    # Note that arrays of structs in dm3 files currently get translated to
    # lists of lists, and as such we have no way of handling that. options are
    # to either convert to a unique standard type (eg tuple of tuples),
    # or a custom type, add a hint to the parser to parse as
    # an array of structs, or simply not support it. (although I think it's
    # needed for complex data types? - in which case we should find a better
    # way of converting it in dm3_to_dictionary)
    ret = {}
    # we convert simple python types to a small subset of DM types
    dm_types = {float: 7,
                int: 3,
                long: 5,
                bool: 8}
    # but we need to convert array types to the proper type.
    # this should mirror the simple types in the grammar
    # (could this be extracted from the grammar itself?)
    """simpledata_2 = h
        simpledata_3 = i
        simpledata_4 = H
        simpledata_5 = I
        simpledata_6 = f
        simpledata_7 = d
        simpledata_8 = b
        simpledata_9 = b
        simpledata_10 = b
        simpledata_11 = q
        simpledata_12 = Q"""
    struct_types = dict(h=2, i=3, H=4, I=5, f=6, d=7, b=8, q=11, Q=12)

    def data_to_dataheader(data):
        ret = dict()
        if isinstance(data, tuple):
            # treat as struct
            ret['dtype'] = 15
            ret['struct_header'] = dict(num_fields=len(data),
                                        types=[dm_types[type(t)] for t in data])
            ret['struct_data'] = dict(data=data)
        elif isinstance(data, array):
            ret['dtype'] = 20
            ret['array_data'] = dict(arraydtype=struct_types[data.typecode],
                                     len=len(data),
                                     array=data)
        else:
            # simple type
            ret['dtype'] = dm_types[type(data)]
            ret['data'] = data
        return ret

    def collection_to_section(d):
        assert isinstance(d, (list, dict))
        if isinstance(d, dict):
            is_dict = True
            items = d.iteritems()
        else:
            is_dict=False
            items = (('', x) for x in d)

        ret = dict(is_dict=is_dict, open=False, num_tags=len(d), data=[])
        for name, data in items:
            if isinstance(data, (list, dict)):
                ret['data'].append(dict(sdtype=20,
                                     name_length=len(name),
                                     name=name,
                                     section=collection_to_section(data)))
            else:
                ret['data'].append(dict(sdtype=21,
                     name_length=len(name),
                     name=name,
                     dataheader=data_to_dataheader(data)))
        return ret
    return dict(section=collection_to_section(d))

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
    #log.setLevel(logging.DEBUG)
    g = ParsedGrammar(dm3_grammar, 'header')
    fname = sys.argv[1] if len(sys.argv) > 1 else "rampint32.dm3"
    print "opening " + fname

    with open(fname, 'rb') as inf:
        out = g.open(inf)
        # any potential reads have to be done with the file still open
        d = dm3_to_dictionary(out)
        # if we want to write this, we need to make sure all fields have been
        # read. Note we don't have to read everything if we just want the image
        # data
        out.to_std_type()
    print "Finished reading!"
    assert len(out['section'].data[0].dataheader.struct_data.data) == 4
    assert out['section'].data[0].name == 'ApplicationBounds'

    write_also = True
    if write_also:
        #log.setLevel(logging.DEBUG)
        with open("out".join(os.path.splitext(fname)), 'wb') as outf:
            out2 = g.save(outf, out.to_std_type())
    #pprint.pprint(out)

    # pprint.pprint(d)
    print "done"

    test_tags = dict_to_dm3(dict(name=45, header=46, dat=dict(
        bob=3, arg=3.151)))
    print test_tags
    with open('test_tags.gtg', 'wb') as outf2:
        #log.setLevel(logging.DEBUG)
        g.save(outf2, test_tags)

    with open('test_tags.gtg', 'rb') as inf2:
        in_test_tags = g.open(inf2)
        print dm3_to_dictionary(in_test_tags)
    # if we want to save an image, need ndarray_to_imagedatadict from
    # dm3_image_utils
    from dm3_image_utils import ndarray_to_imagedatadict
    import numpy as np
    z=np.random.random((512,512))
    z[10:100, 20:80] = 0.5
    with open('test.dm3', 'wb') as outdm3:
        image = ndarray_to_imagedatadict(z)
        ret = {}
        ret["ImageList"] = [{"ImageData": image}]
        # I think ImageSource list creates a mapping between ImageSourceIds and Images
        ret["ImageSourceList"] = [{"ClassName": array('H', "ImageSource:Simple".encode('utf_16_le')), "Id": [0], "ImageRef": 0}]
        # I think this lists the sources for the DocumentObjectlist. The source number is not
        # the indxe in the imagelist but is either the index in the ImageSourceList or the Id
        # from that list. We also need to set the annotation type to identify it as an image
        ret["DocumentObjectList"] = [{"ImageSource": 0, "AnnotationType": 20}]
        # finally some display options
        ret["Image Behavior"] = {"ViewDisplayID": 8}
        ret["InImageMode"] = 1
        g.save(outdm3, dict_to_dm3(ret))