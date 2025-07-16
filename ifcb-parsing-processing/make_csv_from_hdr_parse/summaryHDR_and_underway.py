import pandas as pd
import re
import os

hdrsummary_file = "/Users/sawyer/Desktop/AR82-Pioneer20/ifcb-test-dir/ifcb-parsing-processing/make_csv_from_hdr_parse/hdr_summaries_and_calcs/hdrFileSummaryFULLwithCalcs_2024-04-14.csv"
underway_file = "/Users/sawyer/Desktop/AR82-Pioneer20/ifcb-test-dir/ifcb-parsing-processing/underway_data_processing/mergedunderway_AR82a.csv"

# read in processed file as a dataframe
#df = pd.read_csv(file)

underway_data = pd.read_csv(underway_file)

#underway_data['Datetime_GMT_underway'] = underway_data['Datetime_GMT_underway'].astype(str).str[:-9]

underway_data['Datetime_GMT_underway_2'] = pd.to_datetime(underway_data['Datetime_GMT_underway'])
underway_data['Datetime_GMT_underway_2'] = underway_data['Datetime_GMT_underway_2'].dt.tz_localize(None).strftime('%Y-%m-%d %H:%M:%S')

print(underway_data['Datetime_GMT_underway'])
print(underway_data['Datetime_GMT_underway_2'])
#underway_data.to_csv('test_datetime.csv')
'''
hdrsummary_data = pd.read_csv(hdrsummary_file)

underway_data.reset_index(drop=True, inplace=True)
hdrsummary_data.reset_index(drop=True, inplace=True)

full_merge = pd.merge_asof(hdrsummary_data, underway_data, left_on='Datetime', right_on='Datetime_underway', direction='nearest')

print(underway_data)
print(hdrsummary_data)
'''
