# ---
# jupyter:
#   jupytext:
#     formats: ipynb,py:light
#     text_representation:
#       extension: .py
#       format_name: light
#       format_version: '1.5'
#       jupytext_version: 1.6.0
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# # Check Discrete Sample Summary Format
# This workbook goes through the process of checking a **Discrete Sample Summary** Spreadsheet for the correct format. The parts it checks are:
# 1. Column Headings and Column Order
# 2. Column Elements
#     * Properly formatted
#     * Reasonable or expected values
#     * Has proper fill values
# 3. Completeness
#     * Identify missing or incomplete elements
#
# This is done using teh ```pandas_schema``` library, which works to validate formatting and data of csv or tabular data. It has both off-the-shelf validation tools, such as a regex checker, as well as functionality to pass in custom format checkers.

# #### Import Libraries

import pandas as pd
import numpy as np

# #### Summary Sheet
# Load the summary sheet. Make sure to navigate to the correct directory and have the correct file name entered.

summary_sheet = pd.read_excel("../data/Southern_Ocean-04_NBP1709_Discrete_Sample_Summary_2021-05-05_ACR.xlsx")
summary_sheet.head()

# #### Cruise Names
# Load the R2R list of cruise names. These are the "official" cruise names which should be entered on the spreadsheets.

cruise_information = pd.read_csv("../data/CruiseInformation.csv")
cruise_names = cruise_information["CUID"].to_list()
cruise_names

# ---
# ### Column Headers
# First, need to check that the headers of the columns are both (1) have the correct names and (2) should be in the correct order.

column_headers = pd.read_csv("../data/ColumnHeaders.csv")
# Convert the column headers to the 
column_headers = tuple(column_headers.columns)
for k,column in enumerate(summary_sheet.columns):
    try:
        if column != column_headers[k]:
            # Check if its just not in the correct location
            if column in column_headers:
                ind = column_headers.index(column)
                # Print the results
                print(f"{column} should be moved from position {k} to {ind}")
            else:
                print(f"{column} not an accepted header. Should be '{column_headers[k]}'")
    except IndexError:
        print(f"{column} needs to be deleted.")

# ---
# ## Pandas Schema Validator
# Next, we're going to check the individaul elements of the spreadsheet using the ```pandas_schema``` package to develop column validator schemes for the ship data that is more intuitive that for loops, etc.

from io import StringIO
from pandas_schema import Column, Schema
from pandas_schema.validation import *

# #### Custom Validators
# Next, write a couple of specific functions for checking the cruise data
# * ```check_decimal``` just checks that a value is a floating-point decimal
# * ```check_int``` just checks that a value is an integer
# * ```is_same``` operates on all the values in a column, checking that they are all the same value
#
# These functions get passed into either ```CustomElementValidation``` or ```CustomSeriesValidation``` objects to create a validator which can get passed into ```pandas_schema``` for checking.

# +
from decimal import *

def check_decimal(dec):
    try:
        Decimal(dec)
    except InvalidOperation:
        return False
    return True

def check_int(num):
    try:
        int(num)
    except ValueError:
        return False
    return True

DecimalValidation = CustomElementValidation(lambda d: check_decimal(d), "is not decimal")
IntValidation = CustomElementValidation(lambda d: check_int(d), "is not an integer")


# +
def is_same(series):
    return series == series.mode()[0]

IsSameValidation = CustomSeriesValidation(is_same, "is not the same as other rows")
# -

# ---
# ### Validation Schema
# Next, build the validation schema to check the summary sheet. The checks will differ based on whether the columns are **metadata**, **CTD measurements**, or **Discrete measurements**. There are a few basic checks which I use on the summary sheets:
# * ```InListValidation```: Each element of a column is checked against a list of possible values
# * ```MatchesPatternValidation```: Use regex to check that an element of the column matches the pattern
# * ```InRangeValidation```: Checks that the element of a column is within a (min, max) value. Used to make sure the values are reasonable and physically real.
#

schema = Schema([
    # ---------------------------------------------------------------------------------------
    # Check metadata columns:
    #     Cruise, Station, Target Asset, Start Lat, Start Lon, Start Time, Cast, Bottom Depth
    #     All flag columns checked to start with "*" and be 16-digits long
    Column("Cruise", [InListValidation(cruise_names) | MatchesPatternValidation("-9999999")]),
    Column("Station", [IntValidation]),
    Column("Target Asset", []),
    Column("Start Latitude [degrees]", [InRangeValidation(-90, 90)]),
    Column("Start Longitude [degrees]", [InRangeValidation(-180, 180)]),
    Column("Start Time [UTC]", [DateFormatValidation("%Y-%m-%dT%H:%M:%S.%fZ")]),
    Column("Cast", [IntValidation]),
    Column("Cast Flag", [MatchesPatternValidation(r"\*0|1{16}") | MatchesPatternValidation("-9999999")]),
    Column("Bottom Depth at Start Position [m]", [InRangeValidation(0, 6000) | MatchesPatternValidation("-9999999")]),
    
    # ----------------------------------------------------------------------------------------
    # CTD Data columns: 
    #     These columns correspond to the CTD measurements made at each Niskin bottle closure
    #     All flag columns checked to start with "*" and be 16-digits long
    # CTD Files: Check they end with .hex
    Column("CTD File", [MatchesPatternValidation(r".*\.hex$") | MatchesPatternValidation("-9999999")]),
    Column("CTD File Flag", [MatchesPatternValidation(r"\*0|1{16}") | MatchesPatternValidation("-9999999")]),
    
    # Niskin Bottles: Check they are integers between 0 & 24
    Column("Niskin/Bottle Position", [IntValidation, InRangeValidation(0, 25) | MatchesPatternValidation("-9999999")]),
    Column("Niskin Flag", [MatchesPatternValidation(r"\*0|1{16}") | MatchesPatternValidation("-9999999")]),
    
    # Bottle Closure Time: should be yyyy-mm-ddTHH:MM:SS.sssZ
    Column("CTD Bottle Closure Time [UTC]", [DateFormatValidation("%Y-%m-%dT%H:%M:%S.%fZ") | MatchesPatternValidation("-9999999")]),
    
    # Pressure & Depth: Should be physically reasonable (0 - 6000) and decimal floats
    Column("CTD Pressure [db]", [DecimalValidation, InRangeValidation(0, 6000) | MatchesPatternValidation("-9999999")]),
    Column("CTD Pressure Flag", [MatchesPatternValidation(r"\*0|1{16}") | MatchesPatternValidation("-9999999")]),
    Column("CTD Depth [m]", [DecimalValidation, InRangeValidation(0, 6000) | MatchesPatternValidation("-9999999")]),
    
    # Latitude & Longitude: Should be on Earth & decimal floats
    Column("CTD Latitude [deg]", [DecimalValidation, InRangeValidation(-90, 90)  | MatchesPatternValidation("-9999999")]),
    Column("CTD Longitude [deg]", [DecimalValidation, InRangeValidation(-180, 180) | MatchesPatternValidation("-9999999")]),
    
    # Temperature: Should be within 0 & 35C and decimal floats
    Column("CTD Temperature 1 [deg C]", [DecimalValidation, InRangeValidation(0, 35) | MatchesPatternValidation("-9999999")]),
    Column("CTD Temperature 1 Flag", [MatchesPatternValidation(r"\*0|1{16}") | MatchesPatternValidation("-9999999")]),
    Column("CTD Temperature 2 [deg C]", [DecimalValidation, InRangeValidation(0, 35) | MatchesPatternValidation("-9999999")]),
    Column('CTD Temperature 2 Flag', [MatchesPatternValidation(r"\*0|1{16}") | MatchesPatternValidation("-9999999")]),
    
    # Conductivity: Should be within 0 & 6 and decimal floats
    Column('CTD Conductivity 1 [S/m]', [DecimalValidation, InRangeValidation(0,6) | MatchesPatternValidation("-9999999")]),
    Column('CTD Conductivity 1 Flag', [MatchesPatternValidation(r"\*0|1{16}") | MatchesPatternValidation("-9999999")]),
    Column('CTD Conductivity 2 [S/m]', [DecimalValidation, InRangeValidation(0,6) | MatchesPatternValidation("-9999999")]),
    Column('CTD Conductivity 2 Flag', [MatchesPatternValidation(r"\*0|1{16}") | MatchesPatternValidation("-9999999")]),
    
    # Practical salinity should be within ocean ranges (32, 37) and floats
    Column('CTD Salinity 1 [psu]', [DecimalValidation, InRangeValidation(32, 37) | MatchesPatternValidation("-9999999")]),
    Column('CTD Salinity 2 [psu]', [DecimalValidation, InRangeValidation(32, 37) | MatchesPatternValidation("-9999999")]),
    
    # Dissolved Oxygen & Sat concentrations should be within ocean ranges (0, 9) & decimal floats
    Column('CTD Oxygen [mL/L]', [DecimalValidation, InRangeValidation(0, 9) | MatchesPatternValidation("-9999999")]),
    Column('CTD Oxygen Flag', [MatchesPatternValidation(r"\*0|1{16}") | MatchesPatternValidation("-9999999")]),
    Column('CTD Oxygen Saturation [mL/L]', [DecimalValidation, InRangeValidation(5,9) | MatchesPatternValidation("-9999999")]),
    
    # Fluorescence - we don't measure this, should be fill value -9999999
    Column('CTD Fluorescence [mg/m^3]', [MatchesPatternValidation("-9999999")]),
    Column('CTD Fluorescence Flag', [MatchesPatternValidation("-9999999")]),
    
    # Beam Attenuation (0, 1) and Transmission (0, 100)
    Column('CTD Beam Attenuation [1/m]', [DecimalValidation, InRangeValidation(0,1) | MatchesPatternValidation("-9999999")]),
    Column('CTD Beam Transmission [%]', [DecimalValidation, InRangeValidation(0, 100) | MatchesPatternValidation("-9999999")]),
    Column('CTD Transmissometer Flag', [MatchesPatternValidation(r"\*0|1{16}") | MatchesPatternValidation("-9999999")]),
    
    # CTD pH - we don't measure this
    Column('CTD pH', [MatchesPatternValidation("-9999999")]),
    Column('CTD pH Flag', [MatchesPatternValidation("-9999999")]),
    
    # ----------------------------------------------------------------------------------------
    # Discrete Sample Summaries
    # Oxygen: Ranges should be within physical ocean ranges
    Column('Discrete Oxygen [mL/L]', [DecimalValidation, InRangeValidation(0, 9) | MatchesPatternValidation("-9999999")]),
    Column('Discrete Oxygen Flag', [MatchesPatternValidation(r"\*0|1{16}") | MatchesPatternValidation("-9999999")]),
    Column('Discrete Oxygen Replicate Flag', [MatchesPatternValidation(r"\*0|1{16}") | MatchesPatternValidation("-9999999")]),
    
    # Chlorophyll & Phaeopigment ranges (0, 10); don't collect Fo/Fa ratios
    Column('Discrete Chlorophyll [ug/L]', [DecimalValidation, InRangeValidation(0,10) | MatchesPatternValidation("-9999999")]),
    Column('Discrete Phaeopigment [ug/L]', [DecimalValidation, InRangeValidation(0,10) | MatchesPatternValidation("-9999999")]),
    Column('Discrete Fo/Fa Ratio', [MatchesPatternValidation("-9999999")]),
    Column('Discrete Fluorescence Flag', [MatchesPatternValidation(r"\*0|1{16}") | MatchesPatternValidation("-9999999")]),
    Column('Discrete Fluorescence Replicate Flag', [MatchesPatternValidation(r"\*0|1{16}") | MatchesPatternValidation("-9999999")]),
    
    # Nutrients: Ranges based on physical ocean ranges
    #     Phosphate: Maximum value ~5 uM (WOA 2018 mean fields); check for "<" which means undetecable
    Column('Discrete Phosphate [uM]', [InRangeValidation(0, 5) | MatchesPatternValidation(r"<\d.\d{2}") | MatchesPatternValidation("-9999999")]),
    #     Silicate: Maximum value for Southern Ocean ~120 uM (WOA 2018 mean fields); check for "<" which mean undetectable
    Column('Discrete Silicate [uM]', [InRangeValidation(0, 120)| MatchesPatternValidation(r"<\d.\d{2}") | MatchesPatternValidation("-9999999")]),
    #     Nitrate: Maximum value ~50 uM (WOA 2018 Mean mean fields)
    Column('Discrete Nitrate [uM]', [InRangeValidation(0, 50) | MatchesPatternValidation(r"<\d.\d{2}") | MatchesPatternValidation("-9999999")]),
    #     Nitrite: Maximum values should be < 10; check for "<" which means undetectable
    Column('Discrete Nitrite [uM]', [InRangeValidation(0, 10) | MatchesPatternValidation(r"<\d.\d{2}") | MatchesPatternValidation("-9999999")]),
    #     Ammonium: Maximum values should be < 10; check for "<" which mean undetectable
    Column('Discrete Ammonium [uM]', [InRangeValidation(0, 10) | MatchesPatternValidation(r"<\d.\d{2}") | MatchesPatternValidation("-9999999")]),
    Column('Discrete Nutrients Flag', [MatchesPatternValidation(r"\*0|1{16}") | MatchesPatternValidation("-9999999")]),
    Column('Discrete Nutrients Replicate Flag', [MatchesPatternValidation(r"\*0|1{16}") | MatchesPatternValidation("-9999999")]),
    
    # Salinity: Check that the ranges are within physical ocean ranges
    Column('Discrete Salinity [psu]', [InRangeValidation(33, 37) | MatchesPatternValidation("-9999999")]),
    Column('Discrete Salinity Flag', [MatchesPatternValidation(r"\*0|1{16}") | MatchesPatternValidation("-9999999")]),
    Column('Discrete Salinity Replicate Flag', [MatchesPatternValidation(r"\*0|1{16}") | MatchesPatternValidation("-9999999")]),
    
    # Carbon System measurement: Check within ocean ranges; don't collect/measure pCO2
    #     Alkalinity: Should be between 2200 - 2400
    Column('Discrete Alkalinity [umol/kg]', [InRangeValidation(2200, 2400) | MatchesPatternValidation("-9999999")]),
    Column('Discrete Alkalinity Flag', [MatchesPatternValidation(r"\*0|1{16}") | MatchesPatternValidation("-9999999")]),
    Column('Discrete Alkalinity Replicate Flag', [MatchesPatternValidation(r"\*0|1{16}") | MatchesPatternValidation("-9999999")]),
    #     DIC: Range should be 1900 - 2300
    Column('Discrete DIC [umol/kg]', [InRangeValidation(1900, 2300) | MatchesPatternValidation("-9999999")]),
    Column('Discrete DIC Flag', [MatchesPatternValidation(r"\*0|1{16}") | MatchesPatternValidation("-9999999")]),
    Column('Discrete DIC Replicate Flag', [MatchesPatternValidation(r"\*0|1{16}") | MatchesPatternValidation("-9999999")]),
    #     pCO2: CGSN doesn't measure; should be all fill values
    Column('Discrete pCO2 [uatm]', [InRangeValidation(200, 1200) | MatchesPatternValidation("-9999999")]),
    Column('pCO2 Analysis Temp [deg C]', [DecimalValidation, InRangeValidation(24, 26) | MatchesPatternValidation("-9999999")]),
    Column('Discrete pCO2 Flag', [MatchesPatternValidation(r"\*0|1{16}") | MatchesPatternValidation("-9999999")]),
    Column('Discrete pCO2 Replicate Flag', [MatchesPatternValidation(r"\*0|1{16}") | MatchesPatternValidation("-9999999")]),
    #     pH: Range should be 7 - 9 & Analysis temp 25C
    Column('Discrete pH [Total scale]', [InRangeValidation(7, 9) | MatchesPatternValidation("-9999999")]),
    Column('pH Analysis Temp [deg C]', [DecimalValidation, InRangeValidation(24, 26) | MatchesPatternValidation("-9999999")]),
    Column('Discrete pH Flag', [MatchesPatternValidation(r"\*0|1{16}") | MatchesPatternValidation("-9999999")]),
    Column('Discrete pH Replicate Flag', [MatchesPatternValidation(r"\*0|1{16}") | MatchesPatternValidation("-9999999")]),
    
    # Calculated Carbon System measurement: We don't impute these, should all be fill values
    Column('Calculated Alkalinity [umol/kg]', [MatchesPatternValidation("-9999999")]),
    Column('Calculated DIC [umol/kg]', [MatchesPatternValidation("-9999999")]),
    Column('Calculated pCO2 [uatm]', [MatchesPatternValidation("-9999999")]),
    Column('Calculated pH', [MatchesPatternValidation("-9999999")]),
    Column('Calculated CO2aq [umol/kg]', [MatchesPatternValidation("-9999999")]),
    Column('Calculated Bicarb [umol/kg]', [MatchesPatternValidation("-9999999")]),
    Column('Calculated CO3 [umol/kg]', [MatchesPatternValidation("-9999999")]),
    Column('Calculated Omega-C', [MatchesPatternValidation("-9999999")]),
    Column('Calculated Omega-A', [MatchesPatternValidation("-9999999")])
])

errors = schema.validate(summary_sheet)

for error in errors:
    print(error)

# ---
# ### Metadata Columns
# Next, need to check that all of the metadata columns are the same for each station. We do this on a station-by-station basis.

metadata_columns = ["Cruise", "Station", "Target Asset", "Start Latitude [degrees]", 
                    "Start Longitude [degrees]", "Start Time [UTC]", "Cast",
                   "Bottom Depth at Start Position [m]", "CTD File"]
metadata = summary_sheet[metadata_columns]

# #### Metadata Schema
# Build the schema for validating the metadata information is all the same for each station.

# Rebuild the schema, grouping by input
metadata_schema = Schema([
    Column("Cruise", [IsSameValidation]),
    Column("Station", [IsSameValidation]),
    Column("Target Asset", [IsSameValidation]),
    Column("Start Latitude [degrees]", [IsSameValidation]),
    Column("Start Longitude [degrees]", [IsSameValidation]),
    Column("Start Time [UTC]", [IsSameValidation]),
    Column("Cast", [IsSameValidation]),
    Column("Bottom Depth at Start Position [m]", [IsSameValidation]),
    Column("CTD File", [IsSameValidation]),
])

# Run the validation on a station-by-station basis:

for station in metadata["Station"].unique():
    # Get the data associated with a particular station
    station_data = metadata[metadata["Station"] == station]
    
    # Run it through the validation checker
    merrors = metadata_schema.validate(station_data)
    for error in merrors:
        print(error)




