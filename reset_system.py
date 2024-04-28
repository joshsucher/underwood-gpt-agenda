############## EXTERNAL FUNCTIONS ##############

import underwood_listener

import os
import json
import shutil
from queue import Queue, Empty
import pickle
import requests
from crontab import CronTab
from dotenv import load_dotenv
load_dotenv()

def reset_system(message_queue):
    """Reset the system by deleting configuration files and revoking Google OAuth tokens."""
    
    underwood_listener.clear_queue()

    underwood_listener.send_text("Are you sure you'd like to completely reset the system? This will sever the connection to your Google account, and delete all Wi-Fi settings. Type 'reset' and hit the RETURN key to confirm, or hit the BACKSPACE key to cancel.")

    try:
        raw_data = message_queue.get(timeout=30)
        if raw_data:
            if b'\x7f' in raw_data:  # Check for character 127 (DEL)
                underwood_listener.send_text("Your request to reset the system has been canceled.")
                return
            else:

                choice = raw_data.decode('utf-8').strip().lower()
                if choice == 'reset':
    
                    cron = CronTab(user='root')
                    job_comment = 'generate_agenda_job'
                    jobs = list(cron.find_comment(job_comment))
                    
                    if jobs:
                        job = jobs[0]
                        job.delete()
                        cron.write()

                    prefs_path = '/home/underwood/prefs.json'

                    default_prefs = {
                            'first_boot': True,
                            'lat': None,
                            'lng': None,
                            'fname': None,
                            'lname': None,
                            'city': None,
                            'state': None
                    }

                    # Delete prefs.json
                    if os.path.exists(prefs_path):
                        os.remove(prefs_path)
                        
                    # Create the prefs.json file with default preferences
                    with open(prefs_path, 'w') as file:
                        json.dump(default_prefs, file, indent=4)
                
                    # Optionally, revoke the Google OAuth token
                    revoke_google_oauth_token()
     
                    # Delete token.pickle
                    if os.path.exists('/home/underwood/token.pickle'):
                        os.remove('/home/underwood/token.pickle')

                    # Update wpa_supplicant.conf with new network details
                    underwood_listener.reset_wpa()
                    underwood_listener.send_text("The system has been reset and your Google account has been disconnected. You may now hit the RELOC key to set up a new account, or turn off the machine.")
                    return
                else:
                    underwood_listener.send_text("I'm sorry, I didn't catch that. I'll go ahead and cancel this request, but please feel free to try again!")
                                           
                    return
                return
            return
    except Empty:
        underwood_listener.send_text("I'm sorry, I didn't catch that. I'll go ahead and cancel this request, but please feel free to try again!")
        return

def revoke_google_oauth_token():
    """Revoke the Google OAuth token programmatically if possible."""
    # Assuming token.pickle loads into a Credentials object
    if os.path.exists('/home/underwood/token.pickle'):
        with open('/home/underwood/token.pickle', 'rb') as token:
            creds = pickle.load(token)
            requests.post('https://accounts.google.com/o/oauth2/revoke', params={'token': creds.token},
						  headers={'content-type': 'application/x-www-form-urlencoded'})