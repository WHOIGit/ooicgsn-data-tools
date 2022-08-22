#!/usr/bin/env python
"""
This script modifies WFP file names downloaded from the Subsurface Mooring controller 
in order to be unpacked by the McLane official unpacker. It removes the inductive ID 
number and replaces the file extension to .DAT
"""

import re
import os
import glob

#Directory to the hex data
directory = ''

os.chdir(directory)
file_list = []
for file in glob.glob('A*[0-9].DEC'):
	pattern = re.compile('A\d{3}(\d{4}).DEC')
	new_name = re.sub(pattern, r'A000\g<1>.DAT', file)
	os.rename(file, new_name)
	
for file in glob.glob('C*[0-9].DAT'):
	pattern = re.compile('C\d{3}(\d{4}).DAT')
	new_name = re.sub(pattern, r'C000\g<1>.DAT', file)
	os.rename(file, new_name)

for file in glob.glob('E*[0-9].DAT'):
	pattern = re.compile('E\d{3}(\d{4}).DAT')
	new_name = re.sub(pattern, r'E000\g<1>.DAT', file)
	os.rename(file, new_name)
