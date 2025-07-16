import pandas as pd
import re
import os
import pytz
from datetime import datetime

#the directory containing the csv files from the underway system
##each file is a day, and the file is data collected every minute
dir1 = "/AR82-Pioneer20/AR82_armstrong_underway_data/leg1/proc" # example dir
dir2 = "/AR82-Pioneer20/AR82_armstrong_underway_data/leg2/proc" # example dir

#the regex pattern that will match the correct underway files
file_name_pattern = r'AR\d*_0000.csv'

#compile the regex pattern
pattern_regex = re.compile(file_name_pattern)

#get a list of all csv files in the directory matching the pattern above
csv_files = [file for file in os.listdir(dir2) if pattern_regex.match(file)]

#empty list to store individual dataframes before merge
dfs = []

#iterate over each csv file, read as df, and append to dfs list
for file in csv_files:
    file_path = os.path.join(dir2, file)
    df = pd.read_csv(file_path, header=1)
    dfs.append(df)

#concatenate all dfs in the list into a single df
merged_underway_df = pd.concat(dfs, ignore_index=True)

#print(merged_underway_df)


#change date time cols into one datetime col
#merged_underway_df['Datetime_GMT_underway'] = pd.to_datetime(df['DATE_GMT'] + ' ' + df[' TIME_GMT'])

merged_underway_df['Datetime_GMT_underway'] = merged_underway_df['DATE_GMT'].str.cat(merged_underway_df[' TIME_GMT'], sep = "")
print(merged_underway_df)
def gmt_to_utc(gmt_datetime_str):
    gmt = pytz.timezone('GMT')
    datetime_formats = [
        '%Y/%m/%d %H:%M:%S',
        '%Y-%m-%d %H:%M:%S',
        '%Y/%m/%d %H:%M:%S.%f'
    ]

    for fmt in datetime_formats:
        try:
            gmt_datetime = datetime.strptime(gmt_datetime_str, fmt)
            gmt_localized_datetime = gmt.localize(gmt_datetime)
            utc_datetime = gmt_localized_datetime.astimezone(pytz.utc)
            return utc_datetime
        except ValueError:
            continue
    raise ValueError(f"Time data '{gmt_datetime_str}' does not match any known format")

merged_underway_df['Datetime_UTC_underway'] = merged_underway_df['Datetime_GMT_underway'].apply(gmt_to_utc)

#convert from gmt to utc
print(merged_underway_df['Datetime_GMT_underway'])
merged_underway_df.to_csv("mergedunderway_AR82b.csv", index=False)

#change gmt to utc in datetime col
print('done')
pwd



