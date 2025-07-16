# OOI CGSN IFCB Data Management Repo for IFCB Operators

This repository contains Python scripts that can be used by IFCB operators to process raw IFCB header data for use in OOI IFCB logs and 
OOI IFCB Dashboard Metadata input. 



### Using the Jupyter Notebooks


**IFCB_Log_Notebooks Organization**

These notebooks contain...
* IFCB_Quick_Operator_QC_Checks.ipynb (Verifies that .rois have corresponding .hdr files within a specified directory.)
* IFCB_Log-Underway_IFCB_Data_Processing.ipynb (Creates a .csv of compiled IFCB data to be used to populate the OOI IFCB Log from IFCB underway .hdr files.)
* IFCB_Log-Discrete_IFCB_Data_Processing.ipynb (Creates a .csv of compiled IFCB data to be used to populate the OOI IFCB Log from IFCB discrete .hdr files.)
* Ship_Underway_Lat_and_Lon_Processing.ipynb (Processes and standardizes shipboard data from the R/V Armstrong so lat and lon can be added to underway IFCB data.)
* IFCB_Dashboard_Metadata_CSV.ipynb (Creates metadata for the OOI IFCB Dashboard from the OOI IFBC Log Excel file.)

* /IFCB_Logs (IFCB logs are manually uploaded to this folder; these logs are needed to run IFCB_Dashboard_Metadata_CSV.ipynb.)
* /HDR_Summaries (Contains csvs output from the *_IFCB_Data_Processing.ipynbs; these files are used to create IFCB logs.)
* /Merged_Ship_Underway_Files (Files created by Ship_Underway_Lat_and_Lon_Processing.ipynb + shipboard data; these files are used during the lat & lon processing portions of IFCB_Log-Underway_IFCB_Data_Processing.ipynb.)
* /Metadata_CSVs (Contains files output from IFCB_Dashboard_Metadata_CSV.ipynb, which can be uploaded to the OOI IFCB Dashboard to associate filters and tags with Samples in the UI.) 

**Installation**

1) Clone the repo:

`git clone [repo URL]`

2) Set up a Python environment:

`python -m venv venv
source venv/bin/activate  # On macOS/Linux
venv\Scripts\activate     # On Windows`

3) Install dependencies:

`pip install -r ifcb-parsing-processing/requirements.txt`

4) Launch the Jupyter Notebooks (nativate to the IFCB_Log_Notebooks directory and launch Jupyter)

`cd IFCB_Log_Notebooks
jupyter notebook`



#### Other Python file background/context

**make_csv_from_hdr_parse & underway_data_processing**

These scripts were developed during the first deployment and shipboard ops of the OOI IFCBs. They have since been superseded by the scripts in the Jupyter Notebooks within IFCB_Log_Notebooks.

1. hdr_roi_compare.py 

      used to verify all corrisponding ROI and HDR files are in a directory. Outputs a csv files containing columns for general file name, ROI file name (including extension), and HDR file name (including extension)
      this is independant of the processing order technically; i.e., this doesn't create or cause any dependancies but it can be used as a pre-process qc step

   
3. gather_variables_from_hdr.py

      gathers file_parameters = ["FileComment", "triggerCount", "roiCount", "runTime", "inhibitTime", "humidity", "temperature", "runTime", "PMTAhighVoltage", "PMTBhighVoltage", "humidity", "SyringeSampleVolume", "syringeSamplingSpeed", "temperature", "RunFastFactor", "sampleNumber", "runSampleFast"]
      from hdr files

      outputs a csv where each gathered param is a column and each row represents one hdr file from the designated directory/ies of ifcb data (e.g., hdrFileSummary_2024-08-14.csv)

      this output is used in the hdrSummaryProcessing.py file

4. hdrSummaryProcessing.py

      outputs a csv containing
   
       - Datetime pulled from the file name
   
       - lookTime (lookTime = runTime - inhibitTime)
   
       - runSampleFast_Int
   
       - water_sample_type (in-lab testing, underway, discrete_sample, etc.; taken from file comment)
   
       - flowRate_mins (df['SyringeSampleVolume'] / df['syringeSamplingSpeed'])
   
       - volumeAnalyzed (df['RunFastFactor'] * df['runSampleFast_Int']) * df['flowRate_mins'] * (df['lookTime']/60)/5

       output csv filename example = hdrFileSummaryFULL_2024-08-14.csv

6. summaryHDR_and_underway.py

    merges hdrFileSummaryFULL csv with merged underway ship data.



#### OOI IFCB Dashboard background/context 

- 1 dashboard is used to provide all OOI IFCB data
- Each dataset in the public-facing dashboard represents 1 array (currently there will be 1 total dataset representing Pioneer MAB, this will contain moored, discrete, and underway data from all OOI IFCBs that operate at the Pioneer MAB site)

#### filters and tags

**filters** (these options are fixed in the dashboard)
- Dataset
- Instrument (instrument #)
- Cruise (cruise # by default, we might want to use/force ooi deployment number here instead?)
- Sample Type (discrete, underway, moored)

**tags**
- tags related to targeted sample depths (from water sampling strategy document): "surface", "chlorophyll max", "moored ifcb depth"
- tags related to nearby array site, within 2 km of a given site center (CNSM, etc.)

**latitude and logitude**
these populate the metadata csv, but are added directly to sample metadata in the dashboard, coords do not appear in the filter or tag options after they are added
- discrete samples:
- underway samples: lat and lon coords per sample are taken from ship data coords matched by datetime stamp within 5 minutes of samples. 




