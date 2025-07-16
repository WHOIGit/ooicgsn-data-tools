from datetime import datetime
import pandas as pd
import re

file = "/Volumes/My Passport/IFCB_PLIMS/IFCB_cruise_data/Pioneer20_AR82_IFCB_data/hdrFileSummary_2024-08-14.csv"

# read in processed file as a dataframe
df = pd.read_csv(file)

#drop rows where file names start with and underscore
#df = df.drop(df[df['Filename'].str.contains('._')])
df = df[~df['Filename'].str.startswith('._')]
#df = df.drop(df[df['Filename'].str.contains('_')])

print(df.head())

#Pull date and time from the filename
df['Datetime'] = pd.to_datetime(df['Filename'].str[1:15], format='%Y%m%dT%H%M%S')

#lookTime
df['lookTime'] = df['runTime'] - df['inhibitTime']

### if runsamplefast = false then runsamplefast==1 (correction from what is in original email)
## potentially confirm this is correct, and confirm that where runSampleFast is True - these should be 0

def get_runSampleFast_Int(runSampleFast):
    if runSampleFast == False:
        return 1
    elif runSampleFast == True:
        return 0

df['runSampleFast_Int'] = df['runSampleFast'].apply(get_runSampleFast_Int)

#add a column that indicates underway vs discrete vs other

def get_bin_type(FileComment):
    if re.search("underway", FileComment.lower()):
        return "underway"
    elif re.search("\w\w\d\d", FileComment.lower()):
        return "discrete_sample"
    else:
        return FileComment

df['water_sample_type'] = df['FileComment'].apply(get_bin_type)

#### syringeSamplingSpeed (usually 20 for 20 mins), SyringeSampleVolume (usually 5 ml)
df['flowRate_mins'] = df['SyringeSampleVolume'] / df['syringeSamplingSpeed']

#### volume analyzed calc
df['volumeAnalyzed'] = (df['RunFastFactor'] * df['runSampleFast_Int']) * df['flowRate_mins'] * (df['lookTime']/60)

print(df['volumeAnalyzed'])

df.to_csv("//Volumes/My Passport/IFCB_PLIMS/IFCB_cruise_data/Pioneer20_AR82_IFCB_data/hdrFileSummaryFULL_2024-08-14.csv", index=False)
