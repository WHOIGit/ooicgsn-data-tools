#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@author Christopher Wingard, Stuart Pearce
@brief Reworks the original datateam_ingest code in the datateam_tools
    repository to initiate ingest requests from the command line rather than
    from a prompt and response style of request.
"""
# March 2022 update Stuart Pearce: Adds the ability for user credentials
# from .netrc for different user accounts and wraps the M2M session in
# a class.

import argparse
import netrc
import pprint
import re
import requests
import sys
import time
import logging
import textwrap

import datetime as dt
import dateutil.parser as date_parse
import pandas as pd

from pathlib import Path
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

log_format = "%(levelname)s: %(message)s"
logging.basicConfig(level=logging.WARNING, format=log_format)
logger = logging.getLogger()

PRIORITY = 1
PROD_DOMAIN = "ooinet.oceanobservatories.org"
DEV1_DOMAIN = "ooinet-dev1-west.intra.oceanobservatories.org"
DEV2_DOMAIN = "ooinet-dev2-west.intra.oceanobservatories.org"

#  Instead of creating a requests.Session in the module level
#  namespace, this class creates a session object with stored
#  credentials and calls to the session are object methods to allow 
#  different users.

NETRC_USAGE_NOTE = """
A local .netrc file with "machine" accounts storing OOINet M2M API 
credentials is used for authentication. The .netrc file is expected to 
have an `ooinet.oceanobservatories.org` machine name to use for the 
default credentials. Any additional user M2M accounts can be used 
instead with the `-u` option and should have a .netrc machine name that 
follows the format: username@domain, where `domain` would be the domain 
name of the production, dev01, or dev02 M2M URLs. `username` can be any 
name you choose and doesn't correspond with an OOINet username.
   E.g.: rvanwinkle@ooinet.oceanobservatories.org.

The `login`, `account`, and `password` entries should be the 
API Username, OOINet account email address, and API Token 
respectively.

If the username@domainname format is used in .netrc, 
then it is sufficient to enter the username only and the 
domain name is taken from the `server_target` argument.
   E.g. -u rvanwinkle
 
"""


class m2mSession(object):
    """A class to manage urls, credentials, and a requests session for
    the OOI M2M API systems"""

    def __init__(self, netrc_account, server_target="prod", debug=False):
        """M2M session for ingestion and information requests

        :param netrc_account: str | netrc account name that has the
            api_key, user email address, and api_token credentials stored
        :param server_target: str | `prod`, `dev01`, or `dev02` to select
            which server url base to use.
        :param debug: bool | If True, prints the ingest request instead
            of submitting to the session. Default False.
        :return: json object with the site-node-sensor-deployment specific
            sensor metadata
        """

        # setup constants used to access the data from the different M2M interfaces
        self._debug = debug
        self.session = requests.Session()
        retry = Retry(connect=3, total=4, backoff_factor=0.5)
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount('https://', adapter)
        self.session.headers.update({'Content-Type': 'application/json'})

        # select the base domain name for urls based on `server_target`
        if server_target == 'dev01':
            self._base_dn = DEV1_DOMAIN
        elif server_target == 'dev02':
            self._base_dn = DEV2_DOMAIN
        else:
            self._base_dn = PROD_DOMAIN

        # create the api urls
        self.base_url = 'https://{:s}/api/m2m/'.format(self._base_dn)
        self.deploy_url = self.base_url + '12587/events/deployment/inv/'
        self.ingest_url = self.base_url + '12589/ingestrequest/'

        self._get_credentials(netrc_account)

    def _get_credentials(self, netrc_account):
        """retrieve credentials from .netrc file and apply them them to
        the requests session"""

        # This statement allows the user input to be name only if
        # the account name follows <name>@<ooi-server-target>
        if (
                    not netrc_account.endswith(self._base_dn)
                    and netrc_account != self._base_dn):
            netrc_account = "{:s}@{:s}".format(
                netrc_account, self._base_dn)

        # if the netrc call is given a bad account/machine name, it
        # just returns `None`
        credentials = netrc.netrc().authenticators(netrc_account)
        if not credentials:
            # first try the default
            credentials = netrc.netrc().authenticators(PROD_DOMAIN)
            # then fail with exit if credentials not found.
            if not credentials:
                # Rather than annoying traceback message for a known
                # problem just write the error to the screen and exit
                # with non-zero. This only works nicely though if this
                # class is run as a whole module.
                logger.error(
                    "the netrc account given {:s} returns no "
                    "credentials".format(netrc_account))
                sys.stderr.write('\n')
                sys.exit(1)

        api_key, user_email, api_token = credentials
        self.user_email = user_email
        self.session.auth = (api_key, api_token)

    def get_sensor_information(self, site, node, sensor, deploy):
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
        url = self.deploy_url + "/".join([site, node, sensor, str(deploy)])
        try:
            r = self.session.get(url, timeout=10)
        except requests.exceptions.ConnectTimeout as err:
            logger.error("Could not connect to {:s}".format(self._base_dn))
            sys.exit(2)

        if r.ok:
            return r.json()
        else:
            return

    def ingest_data(self, data_dict):
        """
        Post the ingest request to the OOI M2M api.

        :param data_dict: JSON formatted body of the POST request
        :return r: results of the request
        """
        if self._debug:
            print("---------- submit to ingest ----------")
            print("url={:s}".format(self.ingest_url))
            print(data_dict)
            print("---------- end ----------")
            return

        try:
           r = self.session.post(
                self.ingest_url, json=data_dict, timeout=10)
        except requests.exceptions.ConnectTimeout as err:
            logger.error("Could not connect to {:s}".format(self._base_dn))
            sys.exit(2)
        if r.ok:
            return r
        else:
            return

    def get_deployment_dates(self, site, node, sensor, deploy):
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
        data = self.get_sensor_information(site, node, sensor, deploy)

        # use the metadata to extract the start and end times for the deployment
        if data:
            start = time.strftime(
                '%Y-%m-%dT%H:%M:%S.000Z',
                time.gmtime(data[0]['eventStartTime'] / 1000.))
        else:
            return None, None

        if data[0]['eventStopTime']:
            # check to see if there is a stop time for the deployment, if so use it ...
            stop = time.strftime(
                '%Y-%m-%dT%H:%M:%S.000Z',
                time.gmtime(data[0]['eventStopTime'] / 1000.))
        else:
            # ... otherwise this is an active deployment, no end date
            stop = None

        return start, stop
# --- end m2mSession class ---


def load_ingest_sheet(ingest_csv, ingest_type, ingest_state, user_email):
    """
    Loads the CSV ingest sheet and sets the ingest type used in subsequent steps

    :param ingest_csv: path and file name of the ingest CSV file to use
    :param ingest_type: ingestion type, telemetered (recurring) or recovered
        (once only)
    :param ingest_state: ingesting state, run, stage or mock
    :param user: str, the user email address for the user submitting the
        ingestion.
    :return df: pandas data frame with ingestion parameters
    """
    df = pd.read_csv(ingest_csv, usecols=[0, 1, 2, 3])
    df['username'] = user_email
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


def main(argv=None):
    """
    Reads data from a CSV formatted file using the ingestion CSV structure to
    create and POST an ingest request to the OOI M2M API.

    :param csvfile: CSV file with ingestion information
    :param ingest_type: specifies either a telemetered (recurring) or recovered
        (once only) ingest request type.
    :param netrc_account: string of the user's netrnc "machine" account
        to use for authentication.  Either the full machine name or the
        username when the .netrc machine name is formatted
        as username@domain
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
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description = textwrap.dedent("""
            Sets the source file for the ingests, the type
            and the state and creates an ingest request to M2M."""),
        epilog=NETRC_USAGE_NOTE)

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
    parser.add_argument("--debug", dest="debug", default=False,
                        action="store_true",
                        help="A dry run that prints the final json "
                             "ingest request instead of actually submitting "
                             " to the api for debugging purposes.")
    parser.add_argument("-am", "--use_am_dates", dest="am_dates", default=False,
                        action='store_true', help="Use Asset Management to set start and end dates")
    parser.add_argument("-bd", "--begin_date", dest="begin_date", type=str,
                        help="Date and/or time string to set the start time of the data")
    parser.add_argument("-ed", "--end_date", dest="end_date", type=str,
                        help="Date and/or time string to set the end time of the data")
    parser.add_argument("-st", "--server-target", dest="server_target", type=str,
                        choices=('prod', 'dev01', 'dev02'), default='prod',
                        help="Select the server to ingest data into (default: prod)")
    parser.add_argument("-u", "--user", dest="netrcaccount", type=str,
                        default=PROD_DOMAIN,
                        help= """The user netrnc "machine" name to use 
                              for authentication.  Either the full machine
                              name or the username when the .netrc machine
                              name is formatted as username@domain""")

    # parse the input arguments and create a parser object
    args = parser.parse_args(argv)

    # assign the annotations type and csv file
    ingest_csv = args.csvfile
    ingest_type = args.ingest_type
    netrc_account = args.netrcaccount
    ingest_state = args.ingest_state
    default_review = args.default_review
    am_dates = args.am_dates
    begin_date = args.begin_date
    end_date = args.end_date
    server_target = args.server_target

    #Initialize M2M requests session
    m2m = m2mSession(netrc_account, server_target, debug=args.debug)

    # Initialize empty Pandas DataFrames
    pd.set_option('display.width', 1600)
    ingest_df = pd.DataFrame()

    # load the csv file for the ingests
    df = load_ingest_sheet(ingest_csv, ingest_type, ingest_state, m2m.user_email)
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
                start, stop = m2m.get_deployment_dates(
                    site, node, sensor, row[1].deployment)
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
                r = m2m.ingest_data(ingest_dict)

            else:
                pp.pprint(ingest_dict)
                review = input('Review ingest request. Is this correct? <y>/n: ') or 'y'
                if 'y' in review:
                    r = m2m.ingest_data(ingest_dict)
                    print(r)
                else:
                    print('Skipping this ingest request')
                    continue

            # add the ingest results to the data frame if a successful request was made
            if not args.debug:
                if r is not None and r.status_code == requests.codes.created:
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
                    ingest_df = pd.concat([ingest_df, tdf])
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
