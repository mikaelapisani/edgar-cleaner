#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Apr 23 09:37:40 2019

@author: mikaelapisanileal
"""

import pandas as pd
import numpy as np
import os
from os import listdir
from os.path import isdir, join
import re
import math
import datetime
import sys
if sys.version_info >= (3, 6):
    import zipfile
else:
    import zipfile36 as zipfile

from transfer import TransferData

class Processor:
    def __init__(self, data_path, master_path, results_path):
        self.threshold = 50
        self.error_code_limit = 300
        self.output_size_mb = 5*1000
        self.access_token = "dhZNW6DTN2AAAAAAAAAC2ebJv8jOEPyPNb31b0cf7EtbeVqq8YpRPmiKjLxVT099"
        self.dropbox_folder = "/edgar_test/"
        self.data_path = data_path
        self.master_path = master_path
        self.results_path = results_path

    #function to process one file (a day)
    #data cleaning process
        #   remove crawerls
        #   remove index
        #   remove codes >=error_code_limit
        #   remove robots:  based on the number of unique firms that a given IP address
        #                   downloads on a given day. if it is more than the threshold is a robot.
        #
        # columns to keep:ip,date,time,cik,extention
        # merge with masters' data by accession and cik
    def process_day(self, date_dir, day_file, masters):
        path_day = self.data_path + date_dir + '/' + day_file
        zf = zipfile.ZipFile(path_day)
        zp_list = zipfile.ZipFile.namelist(zf)
        csv_regex = re.compile('(.*)\.csv')
        df = pd.DataFrame(data={})
        for file in zp_list:
            matcher = csv_regex.match(file)
            if (matcher):
                df = pd.read_csv(zf.open(file))
                print("Processing day: " + file)
                print("original size:" + str(df.size))
                
                df = df[(df.crawler == np.float64(0)) & (df.idx == np.float64(0)) & (df.code < self.error_code_limit)]
                df = df[['ip', 'date', 'time', 'cik', 'accession', 'extention']]
                print("after removeing crawerls, index, codes:" + str(df.size))
                
                downloads_count = df.ip.value_counts()
                downloads_count = downloads_count[downloads_count<self.threshold].index
                df = df[df.ip.isin(downloads_count)]
                print("after removing robots:" + str(df.size))
        data_merged = pd.merge(df, masters, how='inner', left_on=['accession', 'cik'], 
                               right_on=['Filename', 'CIK'])
        data_merged = data_merged[['ip', 'date', 'time', 'cik', 'accession', 
                                   'extention', 'Form Type','Date Filed']]
        return data_merged
    
    
    #check if appending the two datasets the size is bigger than output_size_gb
    def check_chunks(self, df1, df2):
        mem_usage_1 = (round(df1.memory_usage(deep=True).sum() / 1024 ** 2, 2))
        mem_usage_2 = (round(df2.memory_usage(deep=True).sum() / 1024 ** 2, 2))
        print((mem_usage_1 + mem_usage_2), 'MG')
        chunks = math.trunc((mem_usage_1 + mem_usage_2)/self.output_size_mb)
        print('chunks=' + str(chunks))
        return (chunks > 0)
    
    #get amount of chunks based on output_size_gb
    def get_chunks(self, df):
        mem_usage_1 = (round(df.memory_usage(deep=True).sum() / 1024 ** 2, 2))
        return math.trunc(mem_usage_1/self.output_size_mb)
    
    #upload file to dropbox 
    def save_csv(self, df, year, idx):
        transferData = TransferData(self.access_token)
        year_idx = year + '_' + str(idx) + '.csv'
        file_from = self.results_path + '/' + year_idx
        file_to = self.dropbox_folder + year_idx
        df.to_csv(file_from, index=False)
        print('Saving file: ' + file_from)
        transferData.upload_file(file_from, file_to)
        os.remove(file_from)    
    
    #divide file into chunks and upload to dropbox          
    def save_data(self, df, year, idx):
        chunks = self.get_chunks(df)
        if (chunks==0):
            self.save_csv(df, year, idx)
            idx+=1
        else:
            for chunk in np.array_split(df, chunks):
                self.save_csv(chunk, year, idx)
                idx+=1
        
    
    #load data from master files and clean it
    def load_master(self, year):
        masters = pd.DataFrame(data={})
        regex_file = re.compile('master' + year + '.*')
       
        for master_file in listdir(self.master_path):
            if (regex_file.match(master_file)):
                master = pd.read_csv(self.master_path + master_file, skiprows=11,
                    names=['CIK','Company Name', 'Form Type', 'Date Filed', 'Filename'],
                    sep='|')
                masters = masters.append(master)
        
        #modify filename data to keep accession number
        masters['Filename'] = masters['Filename'].apply(lambda x: x.split('/')[3].replace('.txt', ''))
        
        #keep columns of interest
        masters = masters[['Filename', 'CIK', 'Form Type','Date Filed']]
        return masters
    
    #process files for determined year
    #for each file process day
    #append to dataframe until the reaches the size
    def process_year(self, year):
        df = pd.DataFrame(data={})
        regex_zip = re.compile('log([0-9]{4})([0-9]{2})([0-9]{2}).zip')
        idx = 0
        masters = self.load_master(year)
        for day_file in listdir(self.data_path + year):
            if regex_zip.match(day_file):
                df_day = self.process_day(year, day_file, masters) 
                if (self.check_chunks(df,df_day)):
                    idx = self.save_csv(df, year, idx)
                    df = df_day
                else:
                    df = df.append(df_day)
        
        if (df.shape[0]>0):
            self.save_data(df, year, idx)        
               
    #for each year folder, process days files
    def process_data(self):
        date_dirs = [f for f in listdir(self.data_path) if isdir(join(self.data_path, f))]
        regex_dir = re.compile('([0-9]{4})')
        for year in date_dirs:
            if (regex_dir.match(year)):
                before = datetime.datetime.now()
                self.process_year(year)
                after = datetime.datetime.now()
                print('time elapsed for year ' + year + ':' + str((after - before)))
     