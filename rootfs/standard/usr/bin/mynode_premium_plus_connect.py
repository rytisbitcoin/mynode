#!/usr/local/bin/python3
import os
import requests
import time
import subprocess
import logging
from inotify_simple import INotify, flags
from systemd import journal
from utilities import *
from device_info import *
from drive_info import *
from application_info import *
from bitcoin_info import *
from lightning_info import *


PREMIUM_PLUS_CONNECT_URL = "https://www.mynodebtc.com/device_api/premium_plus_connect.php"

log = logging.getLogger('premium_plus_connect')
log.addHandler(journal.JournaldLogHandler())
log.setLevel(logging.INFO)
set_logger(log)

# Helper functions
def get_premium_plus_device_info():
    info = {}
    settings = get_premium_plus_settings()

    # Basic Info
    info["serial"] = get_device_serial()
    info["device_type"] = get_device_type()
    info["device_arch"] = get_device_arch()
    info["drive_size"] = get_mynode_drive_size()
    info["data_drive_usage"] = get_data_drive_usage()
    info["os_drive_usage"] = get_os_drive_usage()
    info["temperature"] = get_device_temp()
    info["total_ram"] = get_device_ram()
    info["ram_usage"] = get_ram_usage()
    info["swap_usage"] = get_swap_usage()
    info["uptime"] = get_system_uptime()

    # App status info
    if settings['sync_status']:
        info["app_info"] = get_all_applications_from_json_cache()

    return info

def get_premium_plus_bitcoin_info():
    info = {}
    settings = get_premium_plus_settings()

    if settings['sync_bitcoin_and_lightning']:
        log_message("BITCOIN " + str(get_bitcoin_json_cache()))
        info = get_bitcoin_json_cache()
    return info

def get_premium_plus_lightning_info():
    info = {}
    settings = get_premium_plus_settings()

    if settings['sync_bitcoin_and_lightning']:
        log_message("LIGHTNING " + str(get_lightning_json_cache()))
        info = get_lightning_json_cache()
    return info

# Update hourly
def premium_plus_connect():

    # Check in
    data = {
        "serial": get_device_serial(),
        "version": get_current_version(),
        "token": get_premium_plus_token(),
        "settings": json.dumps(get_premium_plus_settings()),
        "device_info": json.dumps(get_premium_plus_device_info()),
        "bitcoin_info": json.dumps(get_premium_plus_bitcoin_info()),
        "lightning_info": json.dumps(get_premium_plus_lightning_info()),
        "product_key": get_product_key(),
    }

    # Setup tor proxy
    session = requests.session()
    session.proxies = {}
    session.proxies['http'] = 'socks5h://localhost:9050'
    session.proxies['https'] = 'socks5h://localhost:9050'

    # Check In
    fail_count = 0
    premium_plus_connect_success = False
    while not premium_plus_connect_success:
        try:
            # Use tor for check in unless there have been tor 5 failures in a row
            r = None
            if (fail_count+1) % 5 == 0:
                r = requests.post(PREMIUM_PLUS_CONNECT_URL, data=data, timeout=20)
            else:
                r = session.post(PREMIUM_PLUS_CONNECT_URL, data=data, timeout=20)
            
            if r.status_code == 200:
                set_premium_plus_token_status(r.text)
                if r.text == "OK":
                    log_message("Premium+ Connect Success: {}".format(r.text))
                else:
                    log_message("Check In Returned Error: {}".format(r.text))

                os.system("rm -f /tmp/premium_plus_connect_error")
                premium_plus_connect_success = True
            else:
                log_message("Premium+ Connect Failed. Retrying... Code {}".format(r.status_code))
        except Exception as e:
            log_message("Premium+ Connect Failed. Retrying... Exception {}".format(e))

        update_premium_plus_last_sync_time()

        if not premium_plus_connect_success:
            # Check in failed, try again in 1 minute
            set_premium_plus_token_status("CONNECTION_ERROR")
            time.sleep(60)
            fail_count = fail_count + 1

    return True

# Run premium plus update every hour
if __name__ == "__main__":
    one_hour_in_ms = 60 * 60 * 1000

    while True:
        try:
            # Wait for drive to be mounted
            while not is_mynode_drive_mounted():
                log_message("Checking if drive mounted...")
                time.sleep(10)
            log_message("Drive mounted!")

            # Wait on token
            log_message("Looking for Premium+ Token...")
            while not os.path.isfile("/home/bitcoin/.mynode/.premium_plus_token"):
                time.sleep(10)
            log_message("Token found!")
            premium_plus_connect()

            # Watch for updates
            log_message("")
            log_message("Watching for file changes or 1hr...")
            inotify = INotify()
            watch_flags = flags.CREATE | flags.DELETE | flags.MODIFY | flags.DELETE_SELF
            wd = inotify.add_watch('/home/bitcoin/.mynode/', watch_flags)
            for event in inotify.read(timeout=one_hour_in_ms):
                log_message("File changed: " + str(event))
            log_message("Running connect again")
        except Exception as e:
            log_message("Error: {}".format(e))
            time.sleep(60)