**ZPLSC/G Echogram Code & Instructions**  

Author: J. Kuo, jkuo@whoi.edu; S. Petillo, spetillo@whoi.edu; C. Wingard, chris.wingard@oregonstate.edu  
2020-12-21

**Description**

Utilizes [echopype](https://echopype.readthedocs.io/en/latest/), the open-source ocean sonar data processing module, to
process OOI bioacoustic sonar data from both uncabled and cabled array sensors and generate weekly echograms that 
the user community can use to quickly assess the quality and applicability of the data to their research needs.

OOI utilizes the [ASL Environmental Sciences Acoustic Zooplankton Fish Profiler (AZFP)](https://aslenv.com/azfp.html) 
for most uncabled sites (e.g., [CP03ISSM](https://oceanobservatories.org/site/cp03issm/) or 
[GI02HYPM](https://oceanobservatories.org/site/gi02hypm/)). For two of the cabled sites
([CE04OSPS](https://oceanobservatories.org/site/ce04osps/) and [CE02SHBP](https://oceanobservatories.org/site/ce02shbp/)),
OOI uses the [Kongsberg Maritime Simrad EK60 Echo Sounder](https://www.kongsberg.com/maritime/products/mapping-systems/fishery-research/es_scientific/simrad-ek60/). 
Echopype can be used to convert and process data from both sensor types, allowing the generation of a common set of
echograms and processed files.

**Setup:**  

1. Install [Anaconda](https://www.anaconda.com/products/individual) or [Miniconda](https://docs.conda.io/en/latest/miniconda.html)
   to manage Python-related packages and package versions.

2. Create the conda environment to run with this code.

```conda env create --file environment.yml```

3. Activate the Conda environment

```conda activate echopype```

**Usage:**

```python zpls_echogram.py -s [site_code] -d [data_directory] -o [output_directory] -dr [dates] -zm [instrument_type]```

| **Optional flags:** |  |  
| ------------------------ | ----------------------------------- |
| -tc, --tilt_correction   | Apply tilt correction in degree(s) |  
| -dd, --deployed_depth    | The depth where the ZPLSC/G is located at |  
| -cr, --colorbar_range    | Set colorbar range. Usage: "min max" |  
| -vr, --vertical_range    | Set the range for the y-axis. Usage: "min max" |  

| **Required Inputs:** |  |  
| ------------------------- | ----------------------------------- |
| -s, -site_code            | The OOI 8-letter site name for where the ZPLSC/G is located. Ex: "CP03ISSM", "GI02HYPM_Upper", or "GP02HYPM_Lower" |  
| -d, --data_directory      | The path to the root data directory, below which the .01A or .raw files may be found |  
| -o, --output_directory    | The path to the root data directory where .nc file and .png plot will be saved |  
| -dr, --date_range         | The date range to be plotted, e.g.: |  
|                           | "20200118" will plot the day (01/18/2020), |  
|                           | "202001" will plot the whole month (01/01/2020 to 01/31/2020), |  
|                           | "202001 202002" will plot (01/01/2020 to 02/29/2020), |  
|                           | "20200115 20200216" will plot (01/15/2020 to 02/16/2020) |  
| -zm, --zpls_model         | Instrument type, either an EK60 for cabled data, or an AZFP for uncabled |
| -xf, --xml_file           | The path to .xml file to use if the instrument type is an AZFP |  

**Notes:** 

* The root data directory depends on the data source. If looking at cabled data and the EK60, the root data directory 
  is the year (e.g. `2017/`). For uncabled data, the root data directory is `DATA/`.
 
* The path to the `.xml` file is required if the ZPLS model is an AZFP. The `.xml` file contains instrument specific
  settings and calibration coefficients needed to process the data.

* In the case of the global Apex Profiler (subsurface) moorings, the OOI 8-letter site name is appended with either an 
  "_Upper" or "_Lower" to indicate which of the sensors is being used (there are two on the 200 m sphere, one looking 
  up towards the surface, and the other looking down).

* The preset colorbar ranges are the same for every array. Feel free to change it via the optional colorbar_range input.
  
**Raw and Processed Data Folders and Files:**

The raw ZPLS data can be found on the [OOI Raw Data server](https://rawdata.oceanobservatories.org/files/), with the 
directory structure dependent on the ZPLS instrument type (either an EK60 or AZFP).

For the AZFP, the data are organized by the instrument in a folder called `DATA/`, below which the files are organized
in folders named according the year and month (e.g. `201610`). The files are named according to the year, month, day
and hour the data were recorded (e.g. `16101401.01A`). The higher level directory structure above `DATA/` is created by 
OOI technicians. If the ZPLS data from the [Global Argentine Basin, upward looking sensor for Deployment 
3](https://rawdata.oceanobservatories.org/files/GA02HYPM/R00003/instruments/ZPLSG_sn55067/) were downloaded to a local 
folder named `GA`, the folders would look like:

```
./GA/ZPLSG_sn55067/DATA/201610
  ./GA/ZPLSG_sn55067/DATA/201610/16101401.01A
  ./GA/ZPLSG_sn55067/DATA/201610/16101402.01A
  ./GA/ZPLSG_sn55067/DATA/201610/16101403.01A
  ./GA/ZPLSG_sn55067/DATA/201610/*.01A
  ./GA/ZPLSG_sn55067/DATA/201610/16101417.XML
./GA/ZPLSG_sn55067/DATA/201611
  ./GA/ZPLSG_sn55067/DATA/201611/16111401.01A
  ./GA/ZPLSG_sn55067/DATA/201611/16111402.01A
  ./GA/ZPLSG_sn55067/DATA/201611/16111403.01A
  ./GA/ZPLSG_sn55067/DATA/201611/*.01A
```

For the EK60, the data are organized by OOI technicians in folders based on the year, month and day (e.g. `2017/01/01`).
Files are named by the instrument according to the date and time the file was created (e.g. 
`OOI-D20170831-T113333.raw`). If the ZPLS data from the [Coastal Endurance, Oregon Offshore Cabled Shallow Profiler 
Mooring, 200 m Platform](https://rawdata.oceanobservatories.org/files/CE04OSPS/PC01B/ZPLSCB102_10.33.10.143) 
from 2017 were downloaded to local folder named `CE04`, the folders would look like:

```
./CE04/PC01B/ZPLSCB102_10.33.10.143/2017/01/01/
  ./CE04/PC01B/ZPLSCB102_10.33.10.143/2017/01/01/OOI-D20170101-T000000.bot
  ./CE04/PC01B/ZPLSCB102_10.33.10.143/2017/01/01/OOI-D20170101-T000000.idx
  ./CE04/PC01B/ZPLSCB102_10.33.10.143/2017/01/01/OOI-D20170101-T000000.raw
./CE04/PC01B/ZPLSCB102_10.33.10.143/2017/01/02
  ./CE04/PC01B/ZPLSCB102_10.33.10.143/2017/01/02/OOI-D20170102-T000000.bot
  ./CE04/PC01B/ZPLSCB102_10.33.10.143/2017/01/02/OOI-D20170102-T000000.idx
  ./CE04/PC01B/ZPLSCB102_10.33.10.143/2017/01/02/OOI-D20170102-T000000.raw
```

For the AZFP example above, the root data directory would be `./GA/ZPLSG_sn55067/DATA`. For the EK60 example, the root 
data directory would be `./CE04/PC01B/ZPLSCB102_10.33.10.143/2017`. 

Processed data are created in a folder of the users choice. We recommend placing the data at the same level as the root 
data directory in a separate folder called `processed`. The data in the `processed` folder are organized into subfolders 
named according to the date range entered for processing. For example, using the AZFP data from above, if the date range
was 2017-01-01 through 2017-01-08, then the processed data would end up in a folder `20170101-20170108`. The full path
would be `./GA/ZPLSG_sn55067/processed/20170101-20170108/`

There are three types of processed data created by the zpls_echogram script:

1. **Converted**: These are files converted from the raw format (either `.01A` or `.raw`) to NetCDF format (`.nc`) by 
   the echopype convert function. They are 1:1 with the source raw data file. These `.nc` files use the 
   [SONAR-NetCDF4](http://www.ices.dk/sites/pub/Publication%20Reports/Cooperative%20Research%20Report%20(CRR)/CRR341.pdf)
   formatting convention.
2. **Processed**: The echopype process function, taking the converted files as inputs, is used to calculate the volume 
   acoustic backscatter strength (Sv), and the range (distance from the sensor face) in meters. This subset of data is 
   saved in daily `.nc` files that use the site and date range to construct the file name 
   (e.g., data for 2016-01-07 would be saved in 
   `GA02HYPM_Upper_Bioacoustic_Echogram_20170101-20170108_Calibrated_Sv_Full_20170107.nc`).
3. **Averaged**: Takes the processed data one step further and applies temporal averaging (15 minute median averages for
   the coastal ZPLSC and 60 minute median averages for the global ZPLSG) for use in creating the echograms. Missing data
   is filled in via linear interpolation for gaps less than 3x the averaging time window. The averaged data is saved 
   in a `.nc` file using a similar file naming convention as the processed data above (e.g., 
   `GA02HYPM_Upper_Bioacoustic_Echogram_20170101-20170108_Calibrated_Sv_Averaged.nc`).
   
An echogram covering the time period specified by the date range is created from the averaged data and saved along with
the three data types listed above. The files share the same naming convention as the processed and averaged data (e.g., 
`GA02HYPM_Upper_Bioacoustic_Echogram_20170101-20170108_Calibrated_Sv.png`).

**Processing Examples**

The examples below show how to use the script with the different options.

**Example 1:**
```
# set default data directories and .xml file 
GA_DATA="./GA/ZPLSG_sn55067/DATA"
GA_PROC="./GA/ZPLSG_sn55067/processed"
GA_XML="./GA/ZPLSG_sn55067/DATA/201610/16101417.XML"

# set the site, the script will look at the mooring configuration and apply the 
# tilt angle correction (15 degrees for GA02HYPM_Upper) and the design 
# depth (150 m for GA02HYPM_Upper). 
SITE="GA02HYPM_Upper"

# convert and process the data
python zpls_echogram.py -s $SITE -d $GA_DATA -o $GA_PROC -xf $GA_XML -dr 20161115 20161116 -zm AZFP
```
The code will process the data from 2016-11-15 through 2016-11-16. The `.nc` files and `.png` plot will be stored under
`./GA/ZPLSG_sn55067/processed/20161115-20161116/`.

**Example 2:**  
```
python zpls_echogram.py -s $SITE -d $GA_DATA -o $GA_PROC -xf $GA_XML -dr 201611 -zm AZFP
```

The code will process the data for the entire month of November, from 2016-11-01 through 2016-11-30. The `.nc` files 
and `.png` plot will be stored under `./GA/ZPLSG_sn55067/processed/20161101-20161130/`.

**Example 3:**  
```python zpls_echogram.py -s $SITE -d $GA_DATA -o $GA_PROC -xf $GA_XML -dr 201611 -zm AZFP -tc 10```

Change the default tilt correction angle to 10 degrees via the optional `-tc` flag.

**Example 4:**  
```python zpls_echogram.py -s $SITE -d $GA_DATA -o $GA_PROC -xf $GA_XML -dr 201611 -zm AZFP -dd 160```

If the instrument is deployed at 160 m, instead of the design depth of 150 m. The optional flag `-dd 160` will 
override the mooring configuration.

**Example 5:**
```python zpls_echogram.py -s $SITE -d $GA_DATA -o $GA_PROC -xf $GA_XML -dr 201611 -zm AZFP -cr -120 -20 -dd 160```

Change the default colorbar range to -120 to -20 dB via the optional `-cr` flag.

**Example 6:**  
```python zpls_echogram.py -s $SITE -d $GA_DATA -o $GA_PROC -xf $GA_XML -dr 201611 -zm AZFP -vr 0 160 -dd 160```

Change the default vertical range to use 0 to 160 m for the new deployment depth of 160 m via the optional `-vr` flag.
