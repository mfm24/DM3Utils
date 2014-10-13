# setup.py for FileGrammar
from ez_setup import use_setuptools
use_setuptools()

from setuptools import setup, find_packages
setup(
    name = "DM3Utils",
    version = "0.1",
    packages = ['dm_parser'],



    # metadata for upload to PyPI
    author = "Matt Murfitt",
    author_email = "murfitt@gmail.com",
    description = "Utilities for reading and writing Digital Micrograph images",
    license = "License :: OSI Approved :: MIT License",
    url = "https://github.com/mfm24/FileGrammar",   # project home page, if any
    entry_points={
        'gui_scripts': [
            'show_dm_image = dm_parser.show_dm3_file:show_dm_image_script',
        ]
    }
)

