#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@author Christopher Wingard
@brief Reworks the original datateam_ingest code in the datateam_tools
    repository to initiate ingest requests from the command line rather than
    from a prompt and response style of request.
"""
import argparse
import netrc
import pprint
import re
import requests
import sys
import time

import datetime as dt
import dateutil.parser as date_parse
import pandas as pd

from pathlib import Path
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

# initialize requests session
HTTP_STATUS_OK = 200
HEADERS = {
    'Content-Type': 'application/json'
}
PRIORITY = 1

# initialize user credentials and the OOINet base URL
# BASE_URL = 'https://ooinet.oceanobservatories.org'
BASE_URL = 'https://ooinet-west.oceanobservatories.org'
DEPLOY_URL = '12587/events/deployment/inv/'
credentials = netrc.netrc()
API_KEY, USERNAME, API_TOKEN = credentials.authenticators('ooinet-west.oceanobservatories.org')

# setup constants used to access the data from the different M2M interfaces
SESSION = requests.Session()
retry = Retry(connect=5, backoff_factor=0.5)
adapter = HTTPAdapter(max_retries=retry)
SESSION.mount('https://', adapter)


def get_sensor_information(site, node, sensor, deploy):
    """
    Uses the metadata information available from the system for an instrument
    deployment to obtain the asset and calibration information for the
    specified sensor and deployment. This information is part of the sensor
    metadata specific to that deployment.

    :param site: Site name to query
    :param node: Node name to query
    :param sensor: Sensor name to query
    :param deploy: Deployment number
    :return: json object with the site-node-sensor-deployment specific sensor
             metadata
    """
    r = SESSION.get(BASE_URL + '/api/m2m/' + DEPLOY_URL + site + '/' + node + '/' + sensor + '/' + str(deploy),
                    auth=(API_KEY, API_TOKEN))
    if r.status_code == requests.codes.ok:
        return r.json()
    else:
        return None


def get_deployment_dates(site, node, sensor, deploy):
    """
    Based on the site, node and sensor names and the deployment number,
    determine the start and end times for a deployment.

    :param site: Site name to query
    :param node: Node name to query
    :param sensor: Sensor name to query
    :param deploy: Deployment number
    :return: start and stop dates for the deployment of interest
    """
    # request the sensor deployment metadata
    data = get_sensor_information(site, node, sensor, deploy)

    # use the metadata to extract the start and end times for the deployment
    if data:
        start = time.strftime('%Y-%m-%dT%H:%M:%S.000Z', time.gmtime(data[0]['eventStartTime'] / 1000.))
    else:
        return None, None

    if data[0]['eventStopTime']:
        # check to see if there is a stop time for the deployment, if so use it ...
        stop = time.strftime('%Y-%m-%dT%H:%M:%S.000Z', time.gmtime(data[0]['eventStopTime'] / 1000.))
    else:
        # ... otherwise this is an active deployment, no end date
        stop = None

    return start, stop


def load_ingest_sheet(ingest_csv, ingest_type, ingest_state):
    """
    Loads the CSV ingest sheet and sets the ingest type used in subsequent steps

    :param ingest_csv: path and file name of the ingest CSV file to use
    :param ingest_type: ingestion type, telemetered (recurring) or recovered
        (once only)
    :param ingest_state: ingesting state, run, stage or mock
    :return df: pandas data frame with ingestion parameters
    """
    df = pd.read_csv(ingest_csv, usecols=[0, 1, 2, 3])
    df['username'] = USERNAME
    df['deployment'] = get_deployment_number(df.filename_mask.values)
    df['state'] = ingest_state.upper()
    df['priority'] = PRIORITY
    df['type'] = ingest_type.upper()

    return df


def get_deployment_number(filename_mask):
    """
    Pulls the deployment number out of the filename_mask field in the ingest
    CSV file.

    :param filename_mask: filename mask, or regex, in the ingest CSV file that
        includes the deployment number.
    :return deployment_number: the deployment number as an integer
    """
    deployment_number = []
    for fm in filename_mask:
        split_fm = fm.split('/')
        deployment_number.append(int(re.sub('.*?([0-9]*)$', r'\1', split_fm[5])))

    return deployment_number


def build_ingest_dict(ingest_info):
    """
    Converts the pandas dataframe information into the dictionary structure
    needed for the ingest request.

    :param ingest_info: information from the pandas dataframe to use in forming
        the ingest dictionary
    :return request_dict: ingest information structured as a dictionary
    """
    option_dict = {}
    keys = list(ingest_info.keys())

    adict = {k: ingest_info[k] for k in ('parserDriver', 'fileMask', 'dataSource', 'deployment',
                                         'refDes', 'refDesFinal') if k in ingest_info}
    request_dict = dict(username=ingest_info['username'],
                        state=ingest_info['state'],
                        ingestRequestFileMasks=[adict],
                        type=ingest_info['type'],
                        priority=ingest_info['priority'])

    for k in ['beginData', 'endData']:
        if k in keys:
            option_dict[k] = ingest_info[k]

    if option_dict:
        request_dict['options'] = dict(option_dict)

    return request_dict


def ingest_data(url, key, token, data_dict):
    """
    Post the ingest request to the OOI M2M api.

    :param url: Data ingest request URL for the M2M API
    :param key: Ingest users API key (from OOINet)
    :param token: Ingest users API token (from OOINet)
    :param data_dict: JSON formatted body of the POST request
    :return r: results of the request
    """
    r = requests.post('{}/api/m2m/12589/ingestrequest/'.format(url), json=data_dict, headers=HEADERS, auth=(key, token))
    if r.ok:
        return r
    else:
        pass


def main(argv=None):
    """
    Reads data from a CSV formatted file using the ingestion CSV structure to
    create and POST an ingest request to the OOI M2M API.

    :param csvfile: CSV file with ingestion information
    :param ingest_type: specifies either a telemetered (recurring) or recovered
        (once only) ingest request type.
    :param begin_date: the data must be generated by the instrument after this
        date and time (format is 'yyyy-mm-dd' or 'yyyy-mm-dd HH:MM:SS')
    :param end_date: the data must be generated by the instrument before this
        date and time (format is 'yyyy-mm-dd' or 'yyyy-mm-dd HH:MM:SS')
    :return: None, though results are saved as a CSV file in the directory the
        command is called from.
    """
    if argv is None:
        argv = sys.argv[1:]

    # initialize argument parser
    parser = argparse.ArgumentParser(description="""Sets the source file for
                                                    the ingests, the type and
                                                    the state.""")

    # assign input arguments.
    parser.add_argument("-c", "--csvfile", dest="csvfile", type=Path,
                        required=True, help="CSV file with ingest settings")
    parser.add_argument("-t", "--ingest_type", dest="ingest_type", type=str,
                        choices=('recovered', 'telemetered'), required=True,
                        help="Ingest type, either recovered or telemetered")
    parser.add_argument("-s", "--ingest_state", dest="ingest_state", type=str,
                        choices=('run', 'stage', 'mock'), default='run',
                        help="Ingest state, either run, stage or mock (default: run)")
    parser.add_argument("-y", "--default_review", dest="default_review", default=False,
                        action="store_true", help="Set the ingest reviews to default to yes, skipping the review.")
    parser.add_argument("-am", "--use_am_dates", dest="am_dates", default=False,
                        action='store_true', help="Use Asset Management to set start and end dates")
    parser.add_argument("-bd", "--begin_date", dest="begin_date", type=str,
                        help="Date and/or time string to set the start time of the data")
    parser.add_argument("-ed", "--end_date", dest="end_date", type=str,
                        help="Date and/or time string to set the end time of the data")

    # parse the input arguments and create a parser object
    args = parser.parse_args(argv)

    # assign the annotations type and csv file
    ingest_csv = args.csvfile
    ingest_type = args.ingest_type
    ingest_state = args.ingest_state
    default_review = args.default_review
    am_dates = args.am_dates
    begin_date = args.begin_date
    end_date = args.end_date

    # Initialize empty Pandas DataFrames
    pd.set_option('display.width', 1600)
    ingest_df = pd.DataFrame()

    # load the csv file for the ingests
    df = load_ingest_sheet(ingest_csv, ingest_type, ingest_state)
    df = df.sort_values(['deployment', 'reference_designator'])
    df = df.rename(columns={'filename_mask': 'fileMask', 'reference_designator': 'refDes',
                            'data_source': 'dataSource', 'parser': 'parserDriver'})
    df = df[pd.notnull(df['fileMask'])]

    unique_ref_des = list(pd.unique(df.refDes.ravel()))
    unique_ref_des.sort()

    # set cabled platforms to exclude from this process, those use a different method
    cabled = ['RS', 'CE02SHBP', 'CE04OSBP', 'CE04OSPD', 'CE04OSPS']
    cabled_reg_ex = re.compile('|'.join(cabled))
    cabled_ref_des = []
    for rd in unique_ref_des:
        if re.match(cabled_reg_ex, rd):
            cabled_ref_des.append(rd)

    # if the list of unique reference designators contains cabled instruments,
    # remove them from further consideration (they use a different system)
    if cabled_ref_des:
        for x in cabled_ref_des:
            unique_ref_des = [s for s in unique_ref_des if s != x]
            df.drop(df[df['refDes'] == x].index, inplace=True)

    # if all of the reference designators were for cabled systems, we are done
    if df.empty:
        print('Removed cabled array reference designators from the ingestion, no other systems left.')
        return None

    # add refDesFinal
    wcard_refdes = ['GA03FLMA-RIM01-02-CTDMOG000', 'GA03FLMB-RIM01-02-CTDMOG000',
                    'GI03FLMA-RIM01-02-CTDMOG000', 'GI03FLMB-RIM01-02-CTDMOG000',
                    'GP03FLMA-RIM01-02-CTDMOG000', 'GP03FLMB-RIM01-02-CTDMOG000',
                    'GS03FLMA-RIM01-02-CTDMOG000', 'GS03FLMB-RIM01-02-CTDMOG000']

    df['refDesFinal'] = ''
    pp = pprint.PrettyPrinter(indent=2)
    for row in df.iterrows():
        # skip commented out entries
        if '#' in row[1]['parserDriver']:
            continue
        elif row[1]['parserDriver']:
            rd = row[1].refDes
            if rd in wcard_refdes:
                # the CTDMO decoder will be invoked
                row[1].refDesFinal = 'false'
            else:
                # the CTDMO decoder will not be invoked
                row[1].refDesFinal = 'true'

            # create the initial ingest information dictionary
            ingest_info = row[1].to_dict()

            # pull the beginning and ending date/time from Asset Management and use these
            # to bound the ingest request
            if am_dates:
                site, node, sensor = rd.split('-', 2)
                start, stop = get_deployment_dates(site, node, sensor, row[1].deployment)
                if start:
                    ingest_info['beginData'] = start
                if stop:
                    ingest_info['endData'] = stop

            # add the beginning date/time (the data must be generated by the
            # instrument after this date/time) to the dictionary, if set. Note,
            # will replace the date and time from AM if the user also requested
            # the request use those dates.
            if begin_date:
                begin_date = date_parse.parse(begin_date)
                begin_date = begin_date.strftime('%Y-%m-%dT%H:%M:%S.000')
                ingest_info['beginData'] = begin_date

            # add the ending date/time (the data must be generated by the
            # instrument before this date/time) to the dictionary, if set.
            # Note, will replace the date and time from AM if the user also
            # requested the request use those dates.
            if end_date:
                end_date = date_parse.parse(end_date)
                end_date = end_date.strftime('%Y-%m-%dT%H:%M:%S.000')
                ingest_info['endData'] = end_date

            # build and format the ingestion dictionary
            ingest_dict = build_ingest_dict(ingest_info)

            # if the default review is set to True, post the request. otherwise
            # visually review and confirm the request, and post if correct
            if default_review:
                r = ingest_data(BASE_URL, API_KEY, API_TOKEN, ingest_dict)

            else:
                pp.pprint(ingest_dict)
                review = input('Review ingest request. Is this correct? <y>/n: ') or 'y'
                if 'y' in review:
                    r = ingest_data(BASE_URL, API_KEY, API_TOKEN, ingest_dict)
                    print(r)
                else:
                    print('Skipping this ingest request')
                    continue

            # add the ingest results to the data frame if a successful request was made
            if r.status_code == requests.codes.created:
                ingest_json = r.json()
                tdf = pd.DataFrame([ingest_json], columns=list(ingest_json.keys()))
                tdf['ReferenceDesignator'] = row[1]['refDes']
                tdf['state'] = row[1]['state']
                tdf['type'] = row[1]['type']
                tdf['deployment'] = row[1]['deployment']
                tdf['username'] = row[1]['username']
                tdf['priority'] = row[1]['priority']
                tdf['refDesFinal'] = row[1]['refDesFinal']
                tdf['fileMask'] = row[1]['fileMask']
                ingest_df = ingest_df.append(tdf)
            else:
                print('Request failed with status code {}'.format(r.status_code))
                print(r.json())

        else:
            # row[1]['parserDriver'] is empty, should be commented out, but sometimes it isn't
            continue

    # save the results
    print(ingest_df)
    utc_time = dt.datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    ingest_df.to_csv('{}_ingested.csv'.format(utc_time), index=False)


if __name__ == '__main__':
    main()
