import os
import pandas as pd
import re
import chardet

dir = "/Volumes/My Passport/IFCB_PLIMS/IFCB_cruise_data/Pioneer20_AR82_IFCB_data/AR82_shipboard_all_data_ifcb206/"
#moored_dir = "/Volumes/My Passport/199_rois_hdrs_adcs"
#dir = "/Users/sawyer/Desktop/AR82-Pioneer20/ifcb-test-dir"
#print(dir)
#file_parameters = ["triggerCount", "roiCount", "humidity", "temperature", "runTime", "inhibitTime", "PMTAhighVoltage", "PMTBhighVoltage", "FileComment"]

'''
underway samples -> NumberSyringesToAutoRun: 10000
discrete samples -> NumberSyringesToAutoRun: 3
'''

file_parameters = ["FileComment", "triggerCount", "roiCount", "runTime", "inhibitTime", "humidity", "temperature", "runTime",
                       "PMTAhighVoltage", "PMTBhighVoltage", "humidity", "SyringeSampleVolume", "syringeSamplingSpeed", "temperature", "RunFastFactor",
                   "sampleNumber", "runSampleFast"]

all_fileparam_dicts = []


def gather_values(text_content, param_list):
    file_dict = {"Filename": filename}
    for p in param_list:
        escaped_dynamic_string = re.escape(p)
        pattern = re.compile(r'{}:\s*(.+)'.format(escaped_dynamic_string))
        dynamic_match = pattern.search(hdr_content)

        if dynamic_match:
            value = dynamic_match.group(1)
            #return dynamic_match.group(1)
            #print(p, " value: ", value)
            file_dict[p] = value
        else: #return None
            print(filename, "No match found.")

    all_fileparam_dicts.append(file_dict)

#dictionary that allows for only data that has associated roi files to be processed
roi_files = {os.path.splitext(file)[0] for file in os.listdir(dir) if file.endswith(".roi")}

for file in os.listdir(dir):
    if file.endswith(".hdr") and not file.startswith("._"):
        filename = os.path.splitext(file)[0]
        #print(filepath)
        if filename in roi_files:
            filepath = os.path.join(dir, file)
            with open(filepath, "r", encoding="iso-8859-1") as f:
            #print(f)
                hdr_content = f.read()
                #print(hdr_content)
                gather_values(hdr_content, file_parameters)

df = pd.DataFrame(all_fileparam_dicts)



print(df)

df.to_csv("/Volumes/My Passport/IFCB_PLIMS/IFCB_cruise_data/Pioneer20_AR82_IFCB_data/hdrFileSummary_2024-08-14.csv")







