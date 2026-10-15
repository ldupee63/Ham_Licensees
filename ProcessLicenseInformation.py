from bs4 import BeautifulSoup
import requests
import os
import shutil
import zipfile
from pathlib import Path
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, types, text
import warnings
import re
from dataclasses import dataclass, asdict
from typing import List, Tuple, Optional
from datetime import datetime
import csv
from tabulate import tabulate
from typing import cast
import logging 
import sys
import CleanCheckFormat
import gc
import time 
from concurrent.futures import ProcessPoolExecutor

#Handle forked process logging
def worker_log(location : str ,message : str):
    '''
        This logs the processes when they are in parallel.

        Parameters:
            location (str): process identification
            message (str): log message
    '''
    logger = logging.getLogger(__name__)

    record = logger.makeRecord(
        location,
        logging.INFO,
        "",
        0,
        message,
        (),
        None
    )

    return record

#Get the data
def retrieve_zipfile():
    '''
        This goes out to the data repository for the FCC and downloads the license file.
    '''
    logging.info("Getting file from the FCC")
    zipfilepath = "https://data.fcc.gov/download/pub/uls/complete/l_amat.zip"
    # Send a request to the image URL
    response = requests.get(zipfilepath, timeout=300)
    # Check if the request is successful
    if response.status_code == 200:
        # Create the complete file path
        save_path = r"/home/leigh/documents/ULS"
        save_name = "l_amat.zip"
        file_path = os.path.join(save_path, save_name)
        zip_path = Path(save_path) / save_name
        if os.path.exists(zip_path):
            os.remove(zip_path)
            print("Zip file deleted")
        else:
            print("Zip file not found")
        # Open the file and write the zip data
        with open(file_path, 'wb') as file:
            file.write(response.content)
        print(f"Zip successfully saved to {file_path}")
    else:
        print(f"Failed to download zip: status code {response.status_code}")


#expand the zip
def expand_zip():
    '''
        This takes the downloaded zip file and extracts the contents.
    '''
    logging.info("Expanding archive")
    folder_path = r"/home/leigh/documents/ULS/l_amat"

    if os.path.exists(folder_path):
        shutil.rmtree(folder_path)
        print("Folder deleted")
    else:
        print("Folder not found")
    zip_path = r"/home/leigh/documents/ULS/l_amat.zip"
    extract_to = folder_path

    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extract_to)

    print("Zip extracted")
    
    
def clear_tables():
    '''
        We process using staging tables. This allows us to quickly insert the data into the database so we empty the tables first.
        Last comment is teh exception here. This is a table whose content exists only fur a given run.
    '''
    with engine.begin() as connection:
        truncate_statement = text("TRUNCATE TABLE staging_pubacc_am, staging_pubacc_co, staging_pubacc_en, staging_pubacc_hd, staging_pubacc_hs, lastcomment CASCADE;")
        connection.execute(truncate_statement)  

#Get AM Data 
def insert_AM_data(filepath,connection_string) -> logs:
    '''
        This process handles the insertion of the PUBACC_AM file.
        
        Parameters:
            filepath (str): full path to the file
            connection_string (str): string to access the database
    '''
    print(f"Worker started: {os.getpid()}", flush=True)
    logs = []
    location = "Insert_AM"
    logs.append(worker_log(location, "--------------------"))
    logs.append(worker_log(location,f"Starting AM"))
    engine = create_engine(connection_string, pool_pre_ping = True)
    # Define column names and types aligned with the SQL table definition
    columns = [
        'record_type', 'unique_system_identifier', 'uls_file_num', 'ebf_number',
        'callsign', 'operator_class', 'group_code', 'region_code',
        'trustee_callsign', 'trustee_indicator', 'physician_certification', 
        've_signature', 'systematic_callsign_change', 'vanity_callsign_change',
        'vanity_relationship', 'previous_callsign', 'previous_operator_class',
        'trustee_name'
    ]
    try:
        # Read the pipe-delimited file
        logs.append(worker_log(location,f"Reading {filepath}"))
        for df in pd.read_csv(
            filepath,     
            sep="|",
            names=columns,
            dtype=str,
            engine="python",
            keep_default_na=False,
            na_values=[],
            encoding="utf-8",
            chunksize=200000
    ):

            # Convert numeric columns appropriately, ensuring they are not too large
            df['unique_system_identifier'] = pd.to_numeric(df['unique_system_identifier'], errors='coerce')
            df['region_code'] = pd.to_numeric(df['region_code'], downcast='integer', errors='coerce')

            # Trim strings to max length to prevent truncation errors
            df['record_type'] = df['record_type'].str[:2]
            df['uls_file_num'] = df['uls_file_num'].str[:14]
            df['ebf_number'] = df['ebf_number'].str[:30]
            df['callsign'] = df['callsign'].str[:10]
            df['operator_class'] = df['operator_class'].str[:1]
            df['group_code'] = df['group_code'].str[:1]
            df['trustee_callsign'] = df['trustee_callsign'].str[:10]
            df['trustee_indicator'] = df['trustee_indicator'].str[:1]
            df['physician_certification'] = df['physician_certification'].str[:1]
            df['ve_signature'] = df['ve_signature'].str[:1]
            df['systematic_callsign_change'] = df['systematic_callsign_change'].str[:1]
            df['vanity_callsign_change'] = df['vanity_callsign_change'].str[:1]
            df['vanity_relationship'] = df['vanity_relationship'].str[:12]
            df['previous_callsign'] = df['previous_callsign'].str[:10]
            df['previous_operator_class'] = df['previous_operator_class'].str[:1]
            df['trustee_name'] = df['trustee_name'].str[:50]

            # Set missing values to NaN (which translates to NULL in SQL)
            df = df.replace('', np.nan)


            # Use SQLAlchemy to write the dataframe to the SQL database, replacing the existing table
            df.to_sql('staging_pubacc_am', engine, schema='public', if_exists='append', index=False, 
                    dtype={
                        'record_type': types.String(2),
                        'unique_system_identifier': types.Numeric(9, 0),
                        'uls_file_num': types.String(14),
                        'ebf_number': types.String(30),
                        'callsign': types.String(10),
                        'operator_class': types.String(1),
                        'group_code': types.String(1),
                        'region_code': types.Integer(),
                        'trustee_callsign': types.String(10),
                        'trustee_indicator': types.String(1),
                        'physician_certification': types.String(1),
                        've_signature': types.String(1),
                        'systematic_callsign_change': types.String(1),
                        'vanity_callsign_change': types.String(1),
                        'vanity_relationship': types.String(12),
                        'previous_callsign': types.String(10),
                        'previous_operator_class': types.String(1),
                        'trustee_name': types.String(50)
                    }
                    )
    finally:
        engine.dispose()
    logs.append(worker_log(location,"AM data insert complete."))
    print("AM data insert complete.")
    del df
    gc.collect()
    return logs
    
def insert_CO_data(filepath, connection_string) -> logs:
    '''
        This process handles the insertion of the PUBACC_CO file.
        
        Parameters:
            filepath (str): full path to the file
            connection_string (str): string to access the database
    '''
    
    print(f"Worker started: {os.getpid()}", flush=True)
    logs = []
    location = "Insert_CO"
    logs.append(worker_log(location, "--------------------"))
    logs.append(worker_log(location, "Insert CO data"))

    logs.append(worker_log(location, f"Cleaning {filepath}"))
    CleanCheckFormat.file_cleaner(filepath)

    engine = create_engine(connection_string, pool_pre_ping = True)
    # Define column names and types aligned with the SQL table definition
    # Define the column names according to the table schema
    columns = [
        'record_type', 'unique_system_identifier', 'uls_file_num', 'callsign',
        'comment_date', 'description', 'status_code', 'status_date'
    ]

    try:
        # Read the pipe-delimited file
        logs.append(worker_log(location, f"Reading {filepath}"))
        for df in pd.read_csv(
            filepath,     
            sep="|",
            names=columns,
            dtype=str,
            engine="python",
            keep_default_na=False,
            na_values=[],
            encoding="utf-8",
            chunksize=200000
    ):

            # Convert columns to appropriate types
            df['record_type'] = df['record_type'].str[:2]
            df['unique_system_identifier'] = pd.to_numeric(df['unique_system_identifier'], errors='coerce')
            df['uls_file_num'] = df['uls_file_num'].str[:14]
            df['callsign'] = df['callsign'].str[:10]
            df['comment_date'] = df['comment_date'].str[:10]
            df['description'] = df['description'].str[:255]
            df['status_code'] = df['status_code'].str[:1]
            df['status_date'] = pd.to_datetime(df['status_date'], errors='coerce')

        # Ensure not converting 'nan' strings which are meant to be explicit nulls
            df.replace({'nan': np.nan}, inplace=True)

            # Check data types for verification
            #print(df.dtypes)
            #print(df.head())

            # Use SQLAlchemy to write the DataFrame to the SQL database, replacing the existing table
            df.to_sql('staging_pubacc_co', engine, schema='public', if_exists='append', index=False, 
                    dtype={
                        'record_type': types.String(2),
                        'unique_system_identifier': types.Numeric(9, 0),
                        'uls_file_num': types.String(14),
                        'callsign': types.String(10),
                        'comment_date': types.String(10),
                        'description': types.String(255),
                        'status_code': types.String(1),
                        'status_date': types.DateTime()
                    })
            #end chunk
    finally:
        engine.dispose()
    logs.append(worker_log(location, "CO data insert complete."))
    print("CO data insert complete.")
    del df
    gc.collect()
    return logs
    
def insert_EN_data(filepath, connection_string) -> logs:
    '''
        This process handles the insertion of the PUBACC_EN file.
        
        Parameters:
            filepath (str): full path to the file
            connection_string (str): string to access the database
    '''
    
    print(f"Worker started: {os.getpid()}", flush=True)
    logs = []
    location = "Insert EN"
    logs.append(worker_log(location, "--------------------"))
    logs.append(worker_log(location, "Insert EN data"))

    engine = create_engine(connection_string, pool_pre_ping = True)
        # Define the column names according to the table schema
    columns = [
        'record_type', 'unique_system_identifier', 'uls_file_number', 'ebf_number',
        'call_sign', 'entity_type', 'licensee_id', 'entity_name', 'first_name',
        'mi', 'last_name', 'suffix', 'phone', 'fax', 'email', 'street_address',
        'city', 'state', 'zip_code', 'po_box', 'attention_line', 'sgin', 'frn',
        'applicant_type_code', 'applicant_type_other', 'status_code', 'status_date',
        'lic_category_code','linked_license_id','linked_callsign'
    ]
    
    try:
        # Read the pipe-delimited file with specific handling for missing values
        logs.append(worker_log(location, f"Reading {filepath}"))
        for df in pd.read_csv(
            filepath,     
            sep="|",
            names=columns,
            dtype=str,
            engine="python",
            keep_default_na=False,
            na_values=[],
            encoding="utf-8",
            quotechar=None,
            quoting=3,
            chunksize=200000
        ):
        
            # Convert columns to appropriate types
            df['record_type'] = df['record_type'].str[:2]
            df['unique_system_identifier'] = pd.to_numeric(df['unique_system_identifier'], errors='coerce')
            df['uls_file_number'] = df['uls_file_number'].str[:14]
            df['ebf_number'] = df['ebf_number'].str[:30]
            df['call_sign'] = df['call_sign'].str[:10].str.strip()
            df['entity_type'] = df['entity_type'].str[:2]
            df['licensee_id'] = df['licensee_id'].str[:9]
            df['entity_name'] = df['entity_name'].str[:200]
            df['first_name'] = df['first_name'].str[:20].apply(CleanCheckFormat.proper_case_text)
            df['mi'] = df['mi'].str[:1]
            df['last_name'] = df['last_name'].str[:20].apply(CleanCheckFormat.proper_case_text)
            df['suffix'] = df['suffix'].str[:3]
            df['phone'] = df['phone'].str[:10]
            df['fax'] = df['fax'].str[:10]
            df['email'] = df['email'].str[:50]
            df['street_address'] = df['street_address'].str[:60].apply(CleanCheckFormat.normalize_usps_address)
            df['city'] = df['city'].str[:20].apply(CleanCheckFormat.proper_case_text)
            df['state'] = df['state'].str[:2]
            df['zip_code'] = df['zip_code'].str[:9]
            df['po_box'] = df['po_box'].str[:20]
            df['attention_line'] = df['attention_line'].str[:35]
            df['sgin'] = df['sgin'].str[:3]
            df['frn'] = df['frn'].str[:10]
            df['applicant_type_code'] = df['applicant_type_code'].str[:1]
            df['applicant_type_other'] = df['applicant_type_other'].str[:40]
            df['status_code'] = df['status_code'].str[:1]
            df['status_date'] = pd.to_datetime(df['status_date'], errors='coerce')

            # Replace empty strings with NaN
            df.replace('', np.nan, inplace=True)

            
            # Verify data types and contents
            #print(df.dtypes)
            #print(df.head())

            # Insert data into SQL table
            df.to_sql('staging_pubacc_en', engine, schema='public', if_exists='append', index=False, 
                    dtype={
                        'record_type': types.String(2),
                        'unique_system_identifier': types.Numeric(9, 0),
                        'uls_file_number': types.String(14),
                        'ebf_number': types.String(30),
                        'call_sign': types.String(10),
                        'entity_type': types.String(2),
                        'licensee_id': types.String(9),
                        'entity_name': types.String(200),
                        'first_name': types.String(20),
                        'mi': types.String(1),
                        'last_name': types.String(20),
                        'suffix': types.String(3),
                        'phone': types.String(10),
                        'fax': types.String(10),
                        'email': types.String(50),
                        'street_address': types.String(60),
                        'city': types.String(20),
                        'state': types.String(2),
                        'zip_code': types.String(9),
                        'po_box': types.String(20),
                        'attention_line': types.String(35),
                        'sgin': types.String(3),
                        'frn': types.String(10),
                        'applicant_type_code': types.String(1),
                        'applicant_type_other': types.String(40),
                        'status_code': types.String(1),
                        'status_date': types.DateTime()
                    })
            #end chunk
    finally:
        engine.dispose()
    logs.append(worker_log(location, "EN data insert complete."))
    print("EN data insert complete.")
    del df
    gc.collect()
    return logs
    
def insert_HD_data(filepath, connection_string) -> logs:
    '''
        This process handles the insertion of the PUBACC_HD file.
        
        Parameters:
            filepath (str): full path to the file
            connection_string (str): string to access the database
    '''
    
    print(f"Worker started: {os.getpid()}", flush=True)
    logging.info("Start")

    logs = []
    location = "Insert HD"
    logs.append(worker_log(location, "--------------------"))
    logs.append(worker_log(location, "Insert HD data"))
    engine = create_engine(connection_string, pool_pre_ping = True)
    # Define the column names according to the table schema
    columns = [
        'record_type', 'unique_system_identifier', 'uls_file_number', 'ebf_number',
        'call_sign', 'license_status', 'radio_service_code', 'grant_date',
        'expired_date', 'cancellation_date', 'eligibility_rule_num', 'applicant_type_code_reserved',
        'alien', 'alien_government', 'alien_corporation', 'alien_officer',
        'alien_control', 'revoked', 'convicted', 'adjudged', 'involved_reserved',
        'common_carrier', 'non_common_carrier', 'private_comm', 'fixed',
        'mobile', 'radiolocation', 'satellite', 'developmental_or_sta',
        'interconnected_service', 'certifier_first_name', 'certifier_mi',
        'certifier_last_name', 'certifier_suffix', 'certifier_title', 'sex',
        'african_american', 'native_american', 'hawaiian', 'asian', 'white',
        'ethnicity', 'effective_date', 'last_action_date', 'auction_id',
        'reg_stat_broad_serv', 'band_manager', 'type_serv_broad_serv',
        'alien_ruling', 'licensee_name_change', 'whitespace_ind',
        'additional_cert_choice','additional_cert_answer','discontinuation_ind',
        'regulatory_compliance_ind','eligibility_cert_900','transition_plan_cert_900',
        'return_spectrum_cert_900','payment_cert_900'
    ]
    
    #check that the columns defined match the columns from the CSV
    try:
        CleanCheckFormat.check_column_counts(filepath, columns)
    except ValueError as e:
        print(e)
        sys.exit(1)

    try:
        # Read the pipe-delimited file with specific handling for missing values
        logs.append(worker_log(location, f"Reading {filepath}"))
        start = time.perf_counter()
        for df in pd.read_csv(
            filepath,     
            sep="|",
            names=columns,
            dtype=str,
            engine="python",
            keep_default_na=False,
            na_values=[],
            encoding="utf-8",
            chunksize=400000
    ):
            logging.info("Post read")

            logs.append(worker_log(location, f"File read {time.perf_counter() - start}"))
            start = time.perf_counter()
            #check that fields are not too long
            bad, limits = CleanCheckFormat.check_value_length(tablename="pubacc_hd",df=df, engine=engine)
            for col, series in bad.items():
                print(f"Column {col} has {len(series)} values exceeding {limits[col]} characters.")
                print(series.head())


            # Convert columns to appropriate types
            df['record_type'] = df['record_type'].str[:2]
            df['unique_system_identifier'] = pd.to_numeric(df['unique_system_identifier'], errors='coerce')
            df['uls_file_number'] = df['uls_file_number'].str[:14]
            df['ebf_number'] = df['ebf_number'].str[:30]
            df['call_sign'] = df['call_sign'].str[:10]
            # Convert dates to datetime where necessary
            date_columns = ['grant_date', 'expired_date', 'cancellation_date', 'effective_date', 'last_action_date']
            for column in date_columns:
                df[column] = pd.to_datetime(df[column], errors='coerce')
            
            df['auction_id'] = pd.to_numeric(df['auction_id'], errors='coerce')
            

            # Replace empty strings with NaN to allow proper insertion as NULLs in SQL
            df.replace('', np.nan, inplace=True)
            logs.append(worker_log(location, f"File cleaned {time.perf_counter() - start}"))
            logging.info("Post cleaning")
            start = time.perf_counter()
            

            # Insert data into SQL table
            df.to_sql('staging_pubacc_hd', engine, schema='public', if_exists='append', index=False, 
                    dtype={
                        'record_type': types.String(2),
                        'unique_system_identifier': types.Numeric(9, 0),
                        'uls_file_number': types.String(14),
                        'ebf_number': types.String(30),
                        'call_sign': types.String(10),
                        'license_status': types.String(1),
                        'radio_service_code': types.String(2),
                        'grant_date': types.DateTime(),
                        'expired_date': types.DateTime(),
                        'cancellation_date': types.DateTime(),
                        'eligibility_rule_num': types.String(10),
                        'applicant_type_code_reserved': types.String(1),
                        'alien': types.String(1),
                        'alien_government': types.String(1),
                        'alien_corporation': types.String(1),
                        'alien_officer': types.String(1),
                        'alien_control': types.String(1),
                        'revoked': types.String(1),
                        'convicted': types.String(1),
                        'adjudged': types.String(1),
                        'involved_reserved': types.String(1),
                        'common_carrier': types.String(1),
                        'non_common_carrier': types.String(1),
                        'private_comm': types.String(1),
                        'fixed': types.String(1),
                        'mobile': types.String(1),
                        'radiolocation': types.String(1),
                        'satellite': types.String(1),
                        'developmental_or_sta': types.String(1),
                        'interconnected_service': types.String(1),
                        'certifier_first_name': types.String(20),
                        'certifier_mi': types.String(1),
                        'certifier_last_name': types.String(20),
                        'certifier_suffix': types.String(3),
                        'certifier_title': types.String(40),
                        'gender': types.String(1),
                        'african_american': types.String(1),
                        'native_american': types.String(1),
                        'hawaiian': types.String(1),
                        'asian': types.String(1),
                        'white': types.String(1),
                        'ethnicity': types.String(1),
                        'effective_date': types.DateTime(),
                        'last_action_date': types.DateTime(),
                        'auction_id': types.Integer(),
                        'reg_stat_broad_serv': types.String(1),
                        'band_manager': types.String(1),
                        'type_serv_broad_serv': types.String(1),
                        'alien_ruling': types.String(1),
                        'licensee_name_change': types.String(1),
                        'whitespace_ind': types.String(1)

                    })
            #end chunk
            logs.append(worker_log(location, f"to_sql {time.perf_counter() - start}"))
            logging.info("Post to_sql")
    finally:
        engine.dispose()
    logs.append(worker_log(location, "HD data insert complete."))
    print("HD data insert complete.")
    del df
    gc.collect()
    return logs
    
def insert_HS_data(filepath, connection_string) -> logs:
    '''
        This process handles the insertion of the PUBACC_AM file.
        
        Parameters:
            filepath (str): full path to the file
            connection_string (str): string to access the database
        Notes:
            The size of this requires it to be chunked if running in 16gb
    '''
    print(f"Worker started: {os.getpid()}", flush=True)
    logs = []
    location = "Insert HS"
    logs.append(worker_log(location, "--------------------"))
    logs.append(worker_log(location, "Insert HS data"))
    engine = create_engine(connection_string, pool_pre_ping = True)
    # Define the column names according to the table schema
    columns = [
        'record_type', 'unique_system_identifier', 'uls_file_number',
        'callsign', 'log_date', 'code'
    ]
    #print("Columns defined")
    try:
        # Read the pipe-delimited file without altering spaces
        logs.append(worker_log(location, f"Reading {filepath}"))
        for df in pd.read_csv(
            filepath,     
            sep="|",
            names=columns,
            dtype=str,
            engine="python",
            keep_default_na=False,
            na_values=[],
            encoding="utf-8",
            chunksize=1000000
        ):
            # Convert numeric columns appropriately
            df['unique_system_identifier'] = pd.to_numeric(df['unique_system_identifier'], errors='coerce')
            df.replace('', np.nan, inplace=True)


            # Insert data into SQL table
            df.to_sql('staging_pubacc_hs', engine, schema='public', if_exists='append', index=False,
                    dtype={
                        'record_type': types.String(2),
                        'unique_system_identifier': types.Numeric(9, 0),
                        'uls_file_number': types.String(14),
                        'callsign': types.String(10),
                        'log_date': types.String(10),
                        'code': types.String(6)
                    })
    finally:
        engine.dispose()
    logs.append(worker_log(location, "HS data insert complete."))
    print("HS data insert complete.")
    del df
    gc.collect()
    return logs

#procees the data
def process_uls(connection_string):
    '''
        This is the heart of the multithreading.

        Parameters:
            connection_string (str): database access 
    '''
            
    with ProcessPoolExecutor(max_workers=5) as executor:
        futures = [
            executor.submit(insert_AM_data, r'/home/leigh/documents/ULS/l_amat/AM.dat',connection_string),
            executor.submit(insert_CO_data,r'/home/leigh/documents/ULS/l_amat/CO.dat',connection_string),
            executor.submit(insert_EN_data,r'/home/leigh/documents/ULS/l_amat/EN.dat',connection_string),
            executor.submit(insert_HD_data,r'/home/leigh/documents/ULS/l_amat/HD.dat',connection_string),
            executor.submit(insert_HS_data,r'/home/leigh/documents/ULS/l_amat/HS.dat',connection_string)
        ]

        # Wait for all of them to finish
        for future in futures:
            logs = future.result()
            for log in logs:
                logging.getLogger().handle(log)

    logging.info("All file procesing is complete.")

 

#merge in the new data to the working tables
def run_merges():
    '''
        This puts the staging data into the main tables.
        
        Description:
            The data from the staging tables needs to be integrated with the main tables. This cuts down on processing as we are updatating or
            adding information so less of an impact on indexes. All processing is handled through stored procedures in the database, rather than 
            putting the SQL in code.
    '''
    logging.info("Merge data")    
    procedures = [
        "CALL merge_into_PUBACC_AM();",
        "CALL merge_into_PUBACC_EN();",
        "CALL merge_into_PUBACC_HD();",
        "CALL update_PUBACC_CO();",
        "CALL update_PUBACC_HS();"
    ]
    
    with engine.begin() as conn:
        for statement in procedures:
            conn.execute(text(statement))


def get_last_comment():
    '''
        This will create an indexed table with the last comment on a record.
        This should be able to help distinguish between dead accounts and renewing ones
    '''
    insertdata = """  
    insert into lastcomment (unique_system_identifier, code)
    SELECT h.unique_system_identifier, h.code from PUBACC_HS h 
            INNER JOIN (SELECT unique_system_identifier, MAX(log_date) AS log_date FROM PUBACC_HS GROUP BY unique_system_identifier) a
            ON h.unique_system_identifier = a.unique_system_identifier and h.log_date = a.log_date;
    """

    with engine.begin() as conn:
        conn.execute(text(insertdata))




if __name__ == "__main__":
    logging.basicConfig(filename="/home/leigh/projects/ULS/ProcessLicense.log", level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", force=True)
    logging.info("****************************")
    logging.info("Starting run")

    #set up environment variables for your acount information
    username = os.getenv("PG_USER")
    password = os.getenv("PG_PASS")
    server = "localhost"
    port = os.getenv("PG_PORT")
    database = os.getenv("PG_NAME")

    # Define database connection parameters
    connection_string = (f"postgresql://{username}:{password}@{server}:{port}/{database}")
    
    # Create an SQLAlchemy engine
    engine = create_engine(connection_string,    
    pool_size=10,    # Maintain up to 10 connections
    max_overflow=20, # Allow up to 30 extra connections in times of heavy load
    pool_timeout=30, # Wait up to 30 seconds for a connection
    pool_recycle=1800 # Recycle connections after 30 minutes
    )

    #process begins. If it has an issue, you can comment out the individual parts you do not need to run, like retrieving and unzipping the ULS file.
    retrieve_zipfile()
    expand_zip()
    #Load data into DB
    logging.info("Clear tables")
    clear_tables()
    logging.info("Begin data load")
    process_uls(connection_string)
    print("Running merges")
    run_merges()
    logging.info("Creating last comment table")
    get_last_comment()
    logging.info("Complete")