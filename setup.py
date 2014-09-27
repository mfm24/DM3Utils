# setup.py for FileGrammar
from ez_setup import use_setuptools
use_setuptools()

from setuptools import setup, find_packages
setup(
    name = "FileGrammar",
    version = "0.1",
    packages = find_packages(),



    # metadata for upload to PyPI
    author = "Matt Murfitt",
    author_email = "murfitt@gmail.com",
    description = "File grammar for reading and writing binary files",
    license = "License :: OSI Approved :: BSD License",
    keywords = "hello world example examples",
    url = "https://github.com/mfm24/FileGrammar",   # project home page, if any

)
