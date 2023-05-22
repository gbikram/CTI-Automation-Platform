"""
TODO - Upload Logs to MISP 
"""

import os
import time
from apscheduler.schedulers.background import BackgroundScheduler, BlockingScheduler
from ioc_finder import find_iocs
import logging
from rich import print
from rich.logging import RichHandler
logging.basicConfig(level=logging.INFO, filename='logwatcher.log', filemode='w')
from pymisp import MISPEvent, MISPAttribute
import base64
import json
import jmespath

class LogWatcher():

    def __init__(self, logs_dir, misp_client, misp_event_id):
        # Set the directory to monitor
        self.LOGS_DIR = logs_dir

        # Get the initial set of files in the directory
        self.files = set(os.listdir(self.LOGS_DIR))
        self.misp_client = misp_client
        self.misp_event_id = misp_event_id
        misp_event_dict = self.misp_client.get_event(misp_event_id)['Event']
        self.misp_event_obj = MISPEvent()
        self.misp_event_obj.from_dict(**misp_event_dict)
        self.sandbox_tag = 'enriched_via_sandboxs'
    
    def check_new_log(self):
        current_files = set(os.listdir(self.LOGS_DIR))
        logging.info("Current Files: " + str(current_files))
        new_files = current_files - self.files

        if new_files:
            self.process_logs(new_files)
        else:
            logging.info("No new files found")

        self.files = current_files
        logging.info("Resting for 5 seconds")

    def process_logs(self, log_files):
        logging.info("Processing new logs: " + str(log_files))
        for file in log_files:
            if file == 'pestr_log.txt':
                self.process_pestr()
            elif file == 'capa_log.json':
                self.process_capa()

    def process_capa(self):
        logfile_name = 'capa_log.json'
        file_content = self.get_log_file(logfile_name)
        capa_dict = json.loads(file_content)
        artifact_md5 = capa_dict['meta']['sample']['md5']
        attribute = self.get_attribute_by_value(artifact_md5)

        attack_ids = []
        for rule_name in capa_dict['rules']:
            attack_dict = capa_dict['rules'][rule_name]['meta']['attack']
            if len(attack_dict) > 0:
                attack_ids.extend(jmespath.search("[].id", attack_dict))
        if attribute:
            for attack_id in attack_ids:
                attribute.add_tag(attack_id)
            attribute.add_tag('capa')
            self.misp_event_obj.add_attribute(**attribute)
            self.misp_client.update_event(self.misp_event_obj)


    def process_pestr(self):
        """
        Run Strings through ioc-finder to detect any IOCs. 
        Convert those IOCs into MISP attributes and attach to the MISP event.
        """
        logfile_name = 'pestr_log.txt'
        logging.info("Processing {}".format(logfile_name))
        log_file = None
        
        # Read log file
        try:
            log_file = open(f'{self.LOGS_DIR}/{logfile_name}', 'r')
        except Exception as e:
            log_file = open(f'{self.LOGS_DIR}/{logfile_name}', encoding='utf-16')  # Since errors when dumped from Win

        file_content = log_file.read()
        file_content_bytes = file_content.encode("ascii")
        log_file.close()
        iocs = find_iocs(file_content)
        misp_type_mappings = {
            'domains': 'domain',
            'urls': 'url',
            'ipv4s': 'ip-dst',
            'email_addresses': 'email',
            'md5s': 'md5',
            'sha1s': 'sha1',
            'sha256s': 'sha256',
            'bitcoin_addresses': 'btc'
        }
        for ioc_type in misp_type_mappings.keys():
            for ioc in iocs[ioc_type]:
                attribute = self.convert_to_attribute(misp_type_mappings[ioc_type], ioc, 'pestr')
                self.misp_event_obj.add_attribute(**attribute)

        # Upload PEStr file
        self.misp_event_obj.add_attribute(
            'attachment', 
            value=logfile_name,
            data=base64.b64encode(file_content_bytes) 
        )
        self.misp_event_obj.add_tag(self.sandbox_tag)

        ## Push the updated event to MISP
        self.misp_client.update_event(self.misp_event_obj)

    def convert_to_attribute(self, ioc_type, value, analysis_tool):
        logging.info('Converting {} to attribute'.format(value))
        attribute = MISPAttribute(strict=False)
        attribute.value=value
        attribute.type=ioc_type
        attribute.category= 'Artifacts dropped' if ioc_type in ['md5', 'sha1', 'sha256'] else 'Network activity'
        attribute.comment='Source Tool: {}'.format(analysis_tool)
        attribute.add_tag(analysis_tool)
        attribute.add_tag('suspicious')
        return attribute

    def get_attribute_by_value(self, value):
        # Retrieve the attribute from the search result
        logging.info("Searching for {}".format(value))
        search_result = self.misp_client.search(controller='attributes', value=value)
        if 'Attribute' in search_result:
            for attribute in search_result['Attribute']:
                if attribute['value'] == value:
                    logging.info(f"Attribute ID: {attribute['id']}")
                    attribute_obj = MISPAttribute()
                    attribute_obj.from_dict(**attribute)
                    return attribute_obj
        logging.info("Attribute {} not found.".format_map(value))
        return None

    def get_log_file(self, logfile_name):
        try:
            log_file = open(f'{self.LOGS_DIR}/{logfile_name}', 'rb')
        except Exception as e:
            log_file = open(f'{self.LOGS_DIR}/{logfile_name}', encoding='utf-16')
        file_content = log_file.read()
        log_file.close()
        return file_content

    def run(self):
        logging.info("LogWatcher initiated...")
        scheduler = BlockingScheduler() 
        scheduler.add_job(self.check_new_log, 'interval', seconds=5)
        try:
            scheduler.start()
        except KeyboardInterrupt:
            pass