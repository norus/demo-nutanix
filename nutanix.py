#!/usr/bin/env python
import requests
import json
import urllib3
import argparse
import yaml
from pprint import pprint
import logging

# Ignore potential SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Default logger
logger = logging.getLogger()
if logger.handlers:
    for handler in logger.handlers:
        logger.removeHandler(handler)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s.%(msecs)03d %(levelname)s %(module)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S')


class Nutanix:
    def __init__(self, config='config.yml'):
        # Load confg file
        cfg = yaml.load(open(config, 'r'), Loader=yaml.FullLoader)
        self.cfg = cfg

        # Load connection settings from the config
        self.cluster = cfg['cluster']
        self.username = cfg['username']
        self.password = cfg['password']
        self.base_url = 'https://' + self.cluster + '/PrismGateway/services/rest/v2.0/'
        # To get the list of VMs, we need API v3
        # Src: https://github.com/nutanixdev/code-samples/blob/master/postman/Nutanix%20REST%20API%20Testing.postman_collection.json
        self.base_url_v3 = 'https://' + self.cluster + '/api/nutanix/v3/'

        # Load limits from the config
        # Hosts limits
        self.total_cpu_core_limit = cfg['limits']['hosts']['total_cpu_core_limit']
        self.total_memory_usage_gb_limit = cfg['limits']['hosts']['total_memory_usage_gb_limit']
        self.total_storage_usage_gb_limit = cfg['limits']['hosts']['total_storage_usage_gb_limit']
        # VMs limits
        self.total_vms_num_sockets_limit = cfg['limits']['vms']['total_vms_num_sockets_limit']
        self.total_vms_memory_size_gb_limit = cfg['limits']['vms']['total_vms_memory_size_gb_limit']
        self.total_vms_disk_size_gb_limit = cfg['limits']['vms']['total_vms_disk_size_gb_limit']

    # Generic GET to the Nutanix API v2
    def get(self, path):
        conn_url = self.base_url + path
        r = requests.get(conn_url, auth=(self.username, self.password), verify=False)

        return r.json()

    # Generic POST to the Nutanix API v3
    def post_v3(self, path):
        conn_url = self.base_url_v3 + path
        r = requests.post(conn_url, auth=(self.username, self.password), verify=False)

        return r.json()

    # Querying Clusters
    def get_clusters(self):
        cluster_data = self.get('clusters')

        return cluster_data

    # Querying Hosts
    def get_hosts(self):
        host_data = self.get('hosts')

        return host_data

    # Querying VMs
    def get_vms(self):
        vms_data = self.post_v3('vms/list')

        return vms_data



# Main code starts below

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Script to query Nutanix API')
    parser.add_argument('--config', help='Path to config')
    args = parser.parse_args()

    if not args.config:
        parser.print_help()
    else:
        _nutanix = Nutanix(config=args.config)

        #
        # Get data about Clusters
        #
        clusters = _nutanix.get_clusters()


        #
        # Get data about Hosts
        #
        hosts = _nutanix.get_hosts()

        # Counters used to calculate totals for all hosts
        total_hosts_cpu_cores = 0
        total_hosts_cpu_threads = 0
        total_hosts_cpu_sockets = 0
        total_hosts_storage_usage_bytes = 0
        total_hosts_memory_capacity_bytes = 0

        # Count totals for all hosts
        for host in hosts['entities']:
            total_hosts_cpu_cores += host['num_cpu_cores']
            total_hosts_storage_usage_bytes += int(host['usage_stats']['storage.capacity_bytes'])
            total_hosts_memory_capacity_bytes += int(host['memory_capacity_in_bytes'])

        # When the total CPU core limit is reached
        if total_hosts_cpu_cores > _nutanix.total_cpu_core_limit:
            # Add webhooks or other events here
            logger.critical('CPU core limit reached! Current total for all Hosts: {}. Limit: {}'.format(
                total_hosts_cpu_cores, _nutanix.total_cpu_core_limit))

        # When the total memory limit is reached (in GB)
        total_hosts_memory_capacity_gbytes = int(total_hosts_memory_capacity_bytes/1024/1024/1024)
        if total_hosts_memory_capacity_gbytes > _nutanix.total_memory_usage_gb_limit:
            # Add webhooks or other events here
            logger.critical('Memory usage limit reached! Current total for all Hosts: {} GB. Limit: {} GB'.format(
                total_hosts_memory_capacity_gbytes, _nutanix.total_memory_usage_gb_limit))

        # When the total storage limit is reached (in GB)
        total_hosts_storage_usage_gbytes = int(total_hosts_storage_usage_bytes/1024/1024/1024)
        if total_hosts_storage_usage_gbytes > _nutanix.total_storage_usage_gb_limit:
            # Add webhooks or other events here
            logger.critical('Storage usage limit reached! Current total for all Hosts: {} GB. Limit: {} GB'.format(
                total_hosts_storage_usage_gbytes, _nutanix.total_storage_usage_gb_limit))


        #
        # Get data about VMs
        #
        vms = _nutanix.get_vms()

        # Counters used to calculate totals for all VMs
        total_vms_threads_per_core = 0
        total_vms_vcpus_per_socket = 0
        total_vms_num_sockets = 0
        total_vms_memory_size_mib = 0
        total_vms_disk_size_bytes = 0

        # Count totals for all VMs
        for vm in vms['entities']:
            total_vms_threads_per_core += vm['status']['resources']['num_threads_per_core']
            total_vms_vcpus_per_socket += vm['status']['resources']['num_vcpus_per_socket']
            total_vms_num_sockets += vm['status']['resources']['num_sockets']
            total_vms_memory_size_mib += vm['status']['resources']['memory_size_mib']
            # Go through all disks attached to the VM
            for disk in vm['status']['resources']['disk_list']:
                try:
                    total_vms_disk_size_bytes += disk['disk_size_bytes']
                except:
                    pass # Skip storage_containers

        # When the total CPU core limit is reached
        if total_vms_num_sockets > _nutanix.total_vms_num_sockets_limit:
            # Add webhooks or other events here
            logger.critical('CPU sockets limit reached! Current total for all VMs: {}. Limit: {}'.format(
                total_vms_num_sockets, _nutanix.total_vms_num_sockets_limit))

        # When the total memory limit is reached (in GB)
        total_vms_memory_size_gb = int(total_vms_memory_size_mib/1000) # API returns in Mibi, not Mega!
        if total_vms_memory_size_gb > _nutanix.total_vms_memory_size_gb_limit:
            # Add webhooks or other events here
            logger.critical('Memory usage limit reached! Current total for all VMs: {} GB. Limit: {} GB'.format(
                total_vms_memory_size_gb, _nutanix.total_vms_memory_size_gb_limit))

        # When the total storage limit is reached (in GB)
        total_vms_disk_size_gb = int(total_vms_disk_size_bytes/1024/1024/1024)
        if total_vms_disk_size_gb > _nutanix.total_vms_disk_size_gb_limit:
            # Add webhooks or other events here
            logger.critical('Storage usage limit reached! Current total for all VMs: {} GB. Limit: {} GB'.format(
                total_vms_disk_size_gb, _nutanix.total_vms_disk_size_gb_limit))

        # Raw data
        print('\n-- Raw data below --')
        #pprint({'hosts': hosts})
        #pprint({'clusters': clusters})
        #pprint({'vms': vms})
