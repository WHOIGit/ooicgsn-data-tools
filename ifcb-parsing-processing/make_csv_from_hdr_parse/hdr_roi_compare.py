import os
import csv

def scan_directory(directory_path, output_csv):
    # Dictionary to store file names with their respective extensions
    files_data = {}

    # Walk through the directory
    for root, dirs, files in os.walk(directory_path):
        for file in files:
            print(file)
            file_name, file_extension = os.path.splitext(file)
            print(file_name)
            # Only consider .roi and .hdr files
            if file_extension in ['.roi', '.hdr']:
                if file_name not in files_data:
                    files_data[file_name] = {'roi': '', 'hdr': ''}
                # Store the file name in the appropriate column
                if file_extension == '.roi':
                    files_data[file_name]['roi'] = file
                elif file_extension == '.hdr':
                    files_data[file_name]['hdr'] = file

    # Write to CSV
    with open(output_csv, mode='w', newline='') as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["File Name", "ROI File", "HDR File"])  # Writing the header
        for file_name, extensions in files_data.items():
            writer.writerow([file_name, extensions['roi'], extensions['hdr']])  # Writing the file data

    print(f"CSV file '{output_csv}' has been created with file names and extensions.")

# Example usage
directory_path = '/Volumes/My Passport/IFCB_PLIMS/IFCB_cruise_data/Pioneer20_AR82_IFCB_data/AR82_shipboard_all_data_ifcb206'
output_csv = '/Volumes/My Passport/IFCB_PLIMS/IFCB_cruise_data/Pioneer20_AR82_IFCB_data/roi_hdr_compare.csv'
scan_directory(directory_path, output_csv)
