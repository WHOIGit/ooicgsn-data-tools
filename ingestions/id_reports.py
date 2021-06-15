#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@author Collin Dobson
@brief Creates reports for and/or updates the state of an ingestion. This script
    implements code written by Chris Wingard to interact with the OOI M2M API.

    -Usage examples:
        1. To generate a report for ingestion IDs 1 through 100:
            python id_reports.py -si 1 -ei 100 -r

        2. To change the state to "RUN" for ingestion IDs 1 through 100:
            python id_reports.py -si 1 -ei 100 -s run

        3. To change the state to "CANCEL" for ingestion IDs 1 through 5 AND
            generate a report:
            python id_reports.py -si 1 -ei 5 -s cancel -rs
"""
import sys
import netrc
import requests
import argparse
import datetime as dt
import pandas as pd
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

# initialize requests session
HTTP_STATUS_OK = 200
HEADERS = {
    'Content-Type': 'application/json'
}
PRIORITY = 1

# initialize user credentials and the OOINet base URL
#BASE_URL = 'https://ooinet.oceanobservatories.org'
BASE_URL = 'https://ooinet-west.oceanobservatories.org'
credentials = netrc.netrc()
API_KEY, USERNAME, API_TOKEN = credentials.authenticators('ooinet-west.oceanobservatories.org')

# setup constants used to access the data from the different M2M interfaces
SESSION = requests.Session()
retry = Retry(connect=5, backoff_factor=0.5)
adapter = HTTPAdapter(max_retries=retry)
SESSION.mount('https://', adapter)

def flatten_json(y):
    """
    Flattens JSON objects

    :param y: the JSON to flatten
    Sourced from Amir Ziai:
        https://towardsdatascience.com/flattening-json-objects-in-python-f5343c794b10
    """
    out = {}

    def flatten(x, name=''):
        if type(x) is dict:
            for a in x:
                flatten(x[a], name + a + '_')
        elif type(x) is list:
            i = 0
            for a in x:
                flatten(a)
                i += 1
        else:
            out[name[:-1]] = x

    flatten(y)
    return out

def generate_report(ingest_id, key, token, url):
    """
    Queries the OOI M2M API to generate a report for a specific ingestion ID

    :param ingest_id: ingestion ID for which to generate the report
    :param key: Ingest users API key (from OOINet)
    :param token: Ingest users API token (from OOINet)
    :param url: Data ingest request URL for the M2M API
    :return r: results of the request
    """
    request_str = '{}/api/m2m/12589/ingestrequest/'+str(ingest_id)+''
    r = requests.get(request_str.format(url), headers=HEADERS, auth=(key, token))
    if r.ok:
        return r
    else:
        pass

def files_per_id(ingest_id, key, token, url):
    """
    Queries the OOI M2M API to return the number of files in each status after
        a completed ingestion

    :param ingest_id: ingestion ID for which to grab the number of files
    :param key: Ingest users API key (from OOINet)
    :param token: Ingest users API token (from OOINet)
    :param url: Data ingest request URL for the M2M API
    :return r: results of the request
    """
    request_str = '{}/api/m2m/12589/ingestrequest/jobcounts?ingestRequestId='+ \
        str(ingest_id)+'&groupBy=status,state,type,refDes,ingestRequestId'
    r = requests.get(request_str.format(url), headers=HEADERS, auth=(key, token))
    if r.ok:
        return r
    else:
        pass

def change_id_state(ingest_id, new_state, key, token, url):
    """
    Changes the state of a specific ingestion request. For example: to change
        an ingest request from "STAGE" to "RUN" or from "RUN" to "CANCEL".
        Useful for changing requests in bulk.

    :param ingest_id: ingestion ID for which to change the state
    :param new_state: the state to change the request to
    :param key: Ingest users API key (from OOINet)
    :param token: Ingest users API token (from OOINet)
    :param url: Data ingest request URL for the M2M API
    :return r: results of the request
    """
    state_dict = {"id":str(ingest_id), "state":str(new_state)}
    request_str = '{}/api/m2m/12589/ingestrequest/'+str(ingest_id)
    r = requests.put(request_str.format(url), json=state_dict, headers=HEADERS, auth=(key,token))
    return r

def main(argv=None):
    """
    Takes a range of ingestion IDs as input from the user and queries the OOI M2M
        API to produce a report for each ingestion ID and export them to a csv.

        AND/OR

    Takes a range of ingestion IDs as input from a the user and updats their
        state.

    :param startingID: the first ID in the range of IDs specified by the user
    :param endingID: the last ID in the range of IDs specified by the user
    :param report: flag for running an ID report on each ID
    :param stateChange: flag for changing the state of each ID. the new state
        must be supplied by the user.
    :return: None, though results are saved as a CSV file in the directory the
        command is called from.
    """
    if argv is None:
        argv = sys.argv[1:]

    # initialize argument parser
    parser = argparse.ArgumentParser(description="""Takes a range of ingestion
                                                IDs supplied by the user and the
                                                report and/or state change flag.""")

    # assign input arguments.
    parser.add_argument("-si", "--startingID", dest="startingID", type=int,
                        required=True, help="The first ingestion ID \
                        in the range of IDs to work on")
    parser.add_argument("-ei", "--endingID", dest="endingID", type=int,
                        required=False, help="The last ingestion ID \
                        in the range of IDs to work on")
    parser.add_argument("-r", "--report", dest="idReport", default=False,
                        required=False, action='store_true',
                        help="Pass this flag to generate a report for the \
                        specified ingestion IDs")
    parser.add_argument("-s", "--stateChange", dest="stateChange", type=str,
                        choices=('run', 'stage', 'mock', 'cancel', 'suspend',
                        'do nothing'), default='do nothing',
                        help="Pass this parameter to change the state of the \
                        specified ingestion IDs")

    # parse the input arguments and create a parser object
    args = parser.parse_args(argv)

    # assign arguments and flags
    starting_id = args.startingID
    if args.endingID:
        ending_id = args.endingID
    else:
        ending_id = starting_id
    id_report = args.idReport
    state_change = args.stateChange

    # If the stateChange flag was supplied by the user:
    #   -Attempt to change the state of each ID specified to the new state
    #   -Print the result of the state change request to the screen
    if state_change != 'do nothing':
        for i in range(starting_id, ending_id+1):
            new_state = state_change.upper()
            s = change_id_state(i, new_state, API_KEY, API_TOKEN, BASE_URL)
            if (s.status_code == requests.codes.bad):
                print(s.json())

    # If the report flag was supplied by the user:
    #   -Generate a report for each ID specified
    #   -Query the number of files ingested for each ID specified
    #   -Save the results in a csv in the user's current directory
    if id_report:
        # Create a dataframe to store all results
        results_df = pd.DataFrame()
        for i in range(starting_id, ending_id+1):
            # generate ID report
            report = generate_report(i, API_KEY, API_TOKEN, BASE_URL)
            j = report.json()
            j = flatten_json(j)

            # Store everything in a temporary dataframe
            df = pd.DataFrame(j, index=[0], dtype=object)
            df = df[['id', 'type', 'refDes_subsite', 'refDes_node', 'refDes_sensor',
                'status', 'state', 'entryDate', 'username', 'dataSource',
                'options_checkExistingFiles', 'parserDriver', 'fileMask']]
            df = df.infer_objects()

            # Add columns to the temporary dataframe for number of files ingested and
            # their resulting status
            df['SENT'] = 0
            df['QUEUED'] = 0
            df['PENDING'] = 0
            df['RECURRING'] = 0
            df['WAITING'] = 0
            df['COMPLETE'] = 0
            df['WARNING'] = 0
            df['ERROR'] = 0

            # Query the number of files ingested per ID and store the info
            # in the temporary dataframe
            for row in df.iterrows():
                num_files = files_per_id(row[1]['id'], API_KEY, API_TOKEN, BASE_URL)
                json_num_files = num_files.json()
                for i in range(0, len(json_num_files)):
                    status = json_num_files[i]['status']
                    count = json_num_files[i]['count']
                    df[status]=count

            # Append the temporary dataframe to the main dataframe
            results_df = results_df.append(df, sort=False)

        # Store the resulting dataframe in the user's current directory
        utc_time = dt.datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        results_df.to_csv('{}_id_reports.csv'.format(utc_time), index=False)


if __name__ == '__main__':
    main()
