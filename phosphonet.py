#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Jun  3 15:10:08 2019

@author: icervenka

Simple web scraper that downloads lists of kinases that phosphorylate specific
protein residues based on http://www.phosphonet.ca. Takes uniprot protein id as
an input (only human proteins are supported). Several sleep timers are available
for customization to decrease the load on the webpage or avoid disconnect.
This scraper can be used in conjunction with 'pamgene' analysis script to download
the needed phosphorylation data for kinase prediction.
"""

import argparse
import requests
import random
from bs4 import BeautifulSoup
from time import sleep
import numpy as np
import pandas as pd

# ----------------------------------------------------------------------------
# constants
# ----------------------------------------------------------------------------
# urls and class names needed to extract phospho sites
# needs to be updated if website changes
phosphonet_base_url = 'http://www.phosphonet.ca/?search='
phosphonet_kinase_url = 'http://www.phosphonet.ca/kinasepredictor.aspx?uni={}&ps={}'
phos_site_class = "pSiteNameCol"

# number of kinases reported per phospho site (50 as of now)
# TODO maybe move this to parser so the user can specify number of top kinases to return 
num_kinases_per_phos = 50
# each phospho site has currently 7 descriptor values
phos_column_values = 7

# ----------------------------------------------------------------------------
# functions
# ----------------------------------------------------------------------------

def get_phospho_sites(uniprot_id, base_url, tag_class):  
    """
    Scrapes the website for all available phosphosites for specific protein id.

    Parameters
    ----------
    uniprot_id : str
        Human uniprot protein id.
    base_url : str
        Search url of the webpage.
    tag_class : str
        CSS class of element where phosphosite information is stored.

    Returns
    -------
    phospho_sites : list of str
        Phosphosites for uniprot id scraped from the webpage in format
        <single_letter_aa><aa_number>.

    """
    
    url = base_url + uniprot_id
    response = requests.get(url)
    
    # only process if page is OK
    if response.status_code == 200:
        soup = BeautifulSoup(response.text, "html.parser")
        
        # extract all phospho sites based on css class
        phospho_sites = [ x.get_text() for x in soup.findAll("td", {"class": tag_class}) ]
        
    return phospho_sites
     

def get_kinases(uniprot_id, phospho_site, base_url):
    """
    Extracts array of most probable kinases phosphorylating supplied residues of
    specified protein toghether with their scores. phosphonet.ca currently 
    lists 50 top kinases for each residue.

    Parameters
    ----------
    uniprot_id : str
        Human uniprot protein id.
    phospho_site : str
        Protein phosphosite in the format <single_letter_aa><aa_number>.
    base_url : str
        Url for retrieving kinases for specific phosphosite.

    Returns
    -------
    string_array : np.array
        Array of kinases for specific phosphosite with thier characteristics in
        row format.

    """
    
    # Needs to updated if website changes
    kinase_begin_string = "Kinase 1:" 
    string_array = []
    url = base_url.format(uniprot_id, phospho_site)
    response = requests.get(url)
    
    # only process if page is OK
    if response.status_code == 200:
        print("querying kinases for: " + url)
        soup = BeautifulSoup(response.text, "html.parser")
        
        strings = list(soup.html.stripped_strings)
            
        # find where the kinase data begins based on string
        start_index = strings.index(kinase_begin_string)
        
        # end index is number of kinases timess columns plus the offset
        # of the first kinase
        end_index = num_kinases_per_phos * phos_column_values + start_index
        string_array = np.array(strings[start_index:end_index])
        string_array = string_array.reshape((num_kinases_per_phos,
                                             phos_column_values), 
                                            order='C')
    
    return string_array

def kinase_array_to_df(kinase_array, uniprot_id, phospho_site):
    """
    Transforms array of top kinases into pandas DataFrame. Adds phosphosite
    position.


    Parameters
    ----------
    kinase_array : np.array
        Array of kinases generated by 'get_kinases' function.

    Returns
    -------
    df : pandas DataFrame
        Prettified DataFrame of kinases and their characteristics. Includes AA
        position and single letter name.

    """
    
    # convert reshaped array to df
    df = pd.DataFrame(kinase_array)
    # drop unused/duplicated columns
    df.drop([0,4,5], axis=1, inplace=True)
    df.reset_index(inplace=True)
    # rename columns to something useful
    # TODO maybe move to constants section or let user choose
    df.columns = ["kinase_rank", "kinase_name", "kinase_id", "kinexus_score", "kinexus_score_v2"]
    df['kinase_rank'] = df['kinase_rank'] + 1
    # insert the site position and amino acid at the beginning of data frame
    df.insert(0, "site", phospho_site[1:])
    df.insert(0, "aa", phospho_site[0])
    df.insert(0, "substrate", uniprot_id)
    
    return(df)

def typecast_phos_df(phos_df):
    """
    Because all kinase info is scraped from the website as str, numeric columns
    are cast to their appropriate types.

    Parameters
    ----------
    phos_df : pandas DataFrame
        Kinase DataFrame created by 'kinase_array_to_df' function.

    Returns
    -------
    phos_df : pandas DataFrame
        Kinase DataFrame with properly cast types.

    """
    
    # final reorganization of phospho site dataframe
    # cast to proper types
    phos_df['site'] = phos_df['site'].astype(dtype='int32')
    # change comma in kinase name column to semicolon, 
    # otherwise it interferes with csv imports 
    phos_df['kinase_name'] = phos_df['kinase_name'].str.replace(",", ";")
    phos_df['kinexus_score'] = phos_df['kinexus_score'].astype(dtype='int32')        
    phos_df['kinexus_score_v2'] = phos_df['kinexus_score_v2'].astype(dtype='int32')
    phos_df.reset_index(drop=True)
    return phos_df

# ----------------------------------------------------------------------------
# commandline parser
# ----------------------------------------------------------------------------
parser = argparse.ArgumentParser(description='Get protein phosphosites from phosphonet.ca')
parser.add_argument('ids', metavar='uniprot_id', type=str, nargs='+',
                    help='Human uniprot accession numbers of protiens to retrieve')
parser.add_argument('-o', '--outdir', type=str, default='.',
                    help='path where to store output, path must exist (default: current dir)')
parser.add_argument('--sil', type=int, default='2',
                    help='min sleep value between phosphosite queries (default: 2)')
parser.add_argument('--sih', type=int, default='5',
                    help='max sleep value between phosphosite queries (default: 5)')
parser.add_argument('--bs', type=int, default='30',
                    help='number of phosphosites per batch to query between sleep periods (default: 30)')
parser.add_argument('--sbl', type=int, default='30',
                    help='min sleep value between batch queries in seconds (default: 30)')
parser.add_argument('--sbh', type=int, default='40',
                    help='max sleep value between batch queries in seconds (default: 40)')
args = parser.parse_args()

# ----------------------------------------------------------------------------
# main loop for specified ids
# ----------------------------------------------------------------------------
for uniprot_id in args.ids:
    phospho_sites = get_phospho_sites(uniprot_id, phosphonet_base_url, phos_site_class)
    phospho_site_df = pd.DataFrame()
    
    for idx, site in enumerate(phospho_sites):
        kinases = get_kinases(uniprot_id, site, phosphonet_kinase_url)
        kinases = kinase_array_to_df(kinases, uniprot_id, site)
        
        # if first run of the loop, initialize the final df or append otherwise
        if(phospho_site_df.empty):
            phospho_site_df = kinases
        else:
            phospho_site_df = pd.concat([phospho_site_df, kinases])
            
        # sleep periods are introduced to reduce the burden on the server
        # to avoid being kicked out
        # default sleep values make processing not feasible for large number
        # of proteins, but have been tested to work
        # you can speed things up, but might get disconnected
        sleep(random.uniform(args.sil, args.sih))
        if (idx+1)%args.bs == 0:
            print("wating between batches...")
            sleep(random.uniform(args.sbl, args.sbh))
    
    phospho_site_df = typecast_phos_df(phospho_site_df)
    
    # TODO optionally include user supplied score filtering 
    # phos_sites_df.query('kinexus_score>700')
    
    # save to csv
    phospho_site_df.to_csv(args.outdir + "/" + uniprot_id + "_phos_kinexus.csv", 
                           sep=',', 
                           index=False)
    