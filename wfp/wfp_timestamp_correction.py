#!/usr/bin/env python
"""
This script is tailored to Irminger 6 Wire-Following Profiler recovered data only!!

Irminger 6 Wire-Following Profiler recovered data required a correction to the timestamps in the 
raw data due to a bug in firmware version 5.34. This bug caused the profiler to record timestamps 
with year 1940 beginning after the transition from 2019 to 2020.  McLane recommends that 80 years 
be added to the year in all timestamps recorded after 2020-01-01T00:00:00 to correct the timestamp 
in the raw data (1940 + 80 = 2020).

process_a_file iterates through A-files starting from profile 178 (where the time bug began),
and add 80 to the year with value less than 2018. This function only goes through the hex 
string field acm_stop_time.

process_c_file iterates through C-files and add 80 to the year with value less than 2018.
This function does the time correction in the following hex string fields: start_time, stop_time.

process_e_file iterates through E-files and add 80 to the year with value less than 2018.
This function does the time correction in the following hex string fields: timestamp, 
sensor_start_time, sensor_end_time, vehicle_start_time, vehicle_end_time.

process_m_file iterates through M-files and add 80 to the year with value less than 2018. 
This function does the time correction in the following hex string fields: timestamps,
motion_start_time, motion_stop_time.

"""

from struct import *
from datetime import datetime  
from datetime import timedelta
from dateutil.relativedelta import relativedelta
import os
import glob
import re

epoch = datetime.utcfromtimestamp(0)

#-----------------------------------------------------------------------------------------
def process_a_file(directory, profile_count):
	a_file_name = 'A'+str(profile_count).rjust(7,'0')+'.DAT'
	file = os.path.join(directory, a_file_name)
	try: a_file = bytearray(open(file, 'rb').read())
	except: return
	acm_stop_time_bytes = a_file[-4::]

	d = datetime.strptime("01-01-1970", "%m-%d-%Y")
	acm_stop_time = unpack('>i', acm_stop_time_bytes)[0]
	acm_stop_time = (d + timedelta(seconds=acm_stop_time))
	if acm_stop_time < datetime(2018,1,1) and profile_count <= 178:
		new_acm_stop_time = acm_stop_time + relativedelta(years=80)
		new_acm_stop_time = int((new_acm_stop_time - epoch).total_seconds())
		new_acm_stop_time_bytes = pack('>i', new_acm_stop_time)
		a_file[-4::] = new_acm_stop_time_bytes

		write_to_a = open(file, 'wb')
		write_to_a.write(a_file)
		write_to_a.close()
		print(acm_stop_time)
		print(str(profile_count), 'done')

#-----------------------------------------------------------------------------------------
def process_c_file(directory, profile_count):
	c_file_name = 'C'+str(profile_count).rjust(7,'0')+'.DAT'
	file = os.path.join(directory, c_file_name)
	try: c_file = bytearray(open(file, 'rb').read())
	except: return
	end_of_file_index = c_file.find(bytearray.fromhex('ffffffffffffffffffffff'))
	sensor_start_time_bytes = c_file[end_of_file_index+11:end_of_file_index+15]
	sensor_stop_time_bytes = c_file[end_of_file_index+15:end_of_file_index+19]

	d = datetime.strptime("01-01-1970", "%m-%d-%Y")
	start_time = unpack('>i', sensor_start_time_bytes)[0]
	start_time = (d + timedelta(seconds=start_time))
	if start_time < datetime(2018,1,1):
		new_start_time = start_time + relativedelta(years=80)
		new_start_time_seconds = int((new_start_time - epoch).total_seconds())
		new_sensor_start_time_bytes = pack('>i', new_start_time_seconds)
		c_file[end_of_file_index+11:end_of_file_index+15] = new_sensor_start_time_bytes

	stop_time = unpack('>i', sensor_stop_time_bytes)[0]
	stop_time = (d + timedelta(seconds=stop_time))
	if stop_time < datetime(2018,1,1):
		new_stop_time = stop_time + relativedelta(years=80)
		new_stop_time_seconds = int((new_stop_time - epoch).total_seconds())
		new_sensor_stop_time_bytes = pack('>i', new_stop_time_seconds)
		c_file[end_of_file_index+15:end_of_file_index+19] = new_sensor_stop_time_bytes

	write_to_c = open(file, 'wb')
	write_to_c.write(c_file)
	write_to_c.close()

#-----------------------------------------------------------------------------------------
def process_e_file(directory, profile_count):
	e_file_name = 'E'+str(profile_count).rjust(7,'0')+'.DAT'
	file = os.path.join(directory, e_file_name)
	try: e_file = bytearray(open(file, 'rb').read())
	except: return
	profile_message_code = [bytearray.fromhex('fffffffe'),
							bytearray.fromhex('fffffffd'),
							bytearray.fromhex('fffffffc'),
							bytearray.fromhex('fffffffb'),
							bytearray.fromhex('fffffffa')]

	d = datetime.strptime("01-01-1970", "%m-%d-%Y")
	sensor_start_time = unpack('>i', e_file[16:20])[0]
	sensor_start_time = (d + timedelta(seconds=sensor_start_time))
	if sensor_start_time < datetime(2018,1,1):
		new_sensor_start_time = sensor_start_time + relativedelta(years=80)
		new_sensor_start_time_seconds = int((new_sensor_start_time - epoch).total_seconds())
		new_sensor_start_time_bytes = pack('>i', new_sensor_start_time_seconds)
		e_file[16:20] = new_sensor_start_time_bytes

	vehicle_start_time = unpack('>i', e_file[20:24])[0]
	vehicle_start_time = (d + timedelta(seconds=vehicle_start_time))
	if vehicle_start_time < datetime(2018,1,1):
		new_vehicle_start_time = vehicle_start_time + relativedelta(years=80)
		new_vehicle_start_time_seconds = int((new_vehicle_start_time - epoch).total_seconds())
		new_vehicle_start_time_bytes = pack('>i', new_vehicle_start_time_seconds)
		e_file[20:24] = new_vehicle_start_time_bytes

	index = 24
	while e_file[index:index+4] != bytearray.fromhex('ffffffff') and len(e_file) > index:
		if e_file[index:index+4] in profile_message_code:
			index+=8
			restart_time = unpack('>i', e_file[index:index+4])[0]
			restart_time = (d + timedelta(seconds=restart_time))
			if restart_time < datetime(2018,1,1):
				new_restart_time = restart_time + relativedelta(years=80)
				new_restart_time_seconds = int((new_restart_time - epoch).total_seconds())
				new_restart_time_bytes = pack('>i', new_restart_time_seconds)
				e_file[index:index+4] = new_restart_time_bytes
			index+=8
		else:
			time_stamp = unpack('>i', e_file[index:index+4])[0]
			time_stamp = (d + timedelta(seconds=time_stamp))
			if time_stamp < datetime(2018,1,1):
				new_time_stamp = time_stamp + relativedelta(years=80)
				new_time_stamp_seconds = int((new_time_stamp - epoch).total_seconds())
				new_time_stamp_bytes = pack('>i', new_time_stamp_seconds)
				e_file[index:index+4] = new_time_stamp_bytes
			index += 30

	if len(e_file) > index:
		index+=8
		vehicle_end_time = unpack('>i', e_file[index:index+4])[0]
		vehicle_end_time = (d + timedelta(seconds=vehicle_end_time))
		if vehicle_end_time < datetime(2018,1,1):
			new_vehicle_end_time = vehicle_end_time + relativedelta(years=80)
			new_vehicle_end_time_seconds = int((new_vehicle_end_time - epoch).total_seconds())
			new_vehicle_end_time_bytes = pack('>i', new_vehicle_end_time_seconds)
			e_file[index:index+4] = new_vehicle_end_time_bytes

		sensor_end_time = unpack('>i', e_file[index+4:index+8])[0]
		sensor_end_time = (d + timedelta(seconds=sensor_end_time))
		if sensor_end_time < datetime(2018,1,1):
			new_sensor_end_time = sensor_end_time + relativedelta(years=80)
			new_sensor_end_time_seconds = int((new_sensor_end_time - epoch).total_seconds())
			new_sensor_end_time_bytes = pack('>i', new_sensor_end_time_seconds)
			e_file[index+4:index+8] = new_sensor_end_time_bytes

	write_to_e = open(file, 'wb')
	write_to_e.write(e_file)
	write_to_e.close()


#-----------------------------------------------------------------------------------------
def process_m_file(directory, profile_count):
	m_file_name = 'M'+str(profile_count).rjust(7,'0')+'.DAT'
	file = os.path.join(directory, m_file_name)
	try: m_file = bytearray(open(file, 'rb').read())
	except: return
	d = datetime.strptime("01-01-1970", "%m-%d-%Y")

	package_size = unpack('>H', m_file[0:2])[0]
	index = 2
	while len(m_file)-index > 64:
		time_stamp = unpack('>i', m_file[index:index+4])[0]
		time_stamp = (d + timedelta(seconds=time_stamp))
		if time_stamp < datetime(2018,1,1):
			new_time_stamp = time_stamp + relativedelta(years=80)
			new_time_stamp_seconds = int((new_time_stamp - epoch).total_seconds())
			new_time_stamp_bytes = pack('>i', new_time_stamp_seconds)
			m_file[index:index+4] = new_time_stamp_bytes
		index += package_size
	index+=package_size

	if len(m_file) > index:
		motion_start_time = unpack('>i', m_file[index:index+4])[0]
		motion_start_time = (d + timedelta(seconds=motion_start_time))
		if motion_start_time < datetime(2018,1,1):
			new_motion_start_time = motion_start_time + relativedelta(years=80)
			new_motion_start_time_seconds = int((new_motion_start_time - epoch).total_seconds())
			new_motion_start_time_bytes = pack('>i', new_motion_start_time_seconds)
			m_file[index:index+4] = new_motion_start_time_bytes

		motion_end_time = unpack('>i', m_file[index+4:index+8])[0]
		motion_end_time = (d + timedelta(seconds=motion_end_time))
		if motion_end_time < datetime(2018,1,1):
			new_motion_end_time = motion_end_time + relativedelta(years=80)
			new_motion_end_time_seconds = int((new_motion_end_time - epoch).total_seconds())
			new_motion_end_time_bytes = pack('>i', new_motion_end_time_seconds)
			m_file[index+4:index+8] = new_motion_end_time_bytes

	write_to_m = open(file, 'wb')
	write_to_m.write(m_file)
	write_to_m.close()


directory = ''
os.chdir(directory)
file_list = []
for file in glob.glob('?*[0-9].DAT'):
	file_list.append(int(re.findall('.(\d+).DAT', file)[0]))
total_profile = max(file_list)


for profile_count in range(0, total_profile+1):
	print(profile_count)
	process_a_file(directory, profile_count)
	try: process_c_file(directory, profile_count)
	except: pass
	process_e_file(directory, profile_count)
	process_m_file(directory, profile_count)

