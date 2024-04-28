#!/usr/bin/env python3

############## EXTERNAL FUNCTIONS ##############

import underwood_listener
from schedule_agenda import schedule_agenda

############## DEPENDENCIES ##############

#SYS

from datetime import datetime, timedelta
import pytz
import time
import os
import sys
import subprocess
from queue import Queue, Empty
from dotenv import load_dotenv
load_dotenv()
import pytz
from tzlocal import get_localzone, get_localzone_name
from zoneinfo import ZoneInfo
import threading

#API

import re
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
import socketserver
from urllib.parse import urlparse, parse_qs
import pickle
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from openai import OpenAI

#TXT

import json

def load_preferences():
    """Load preferences from a JSON file, create the file with default settings if it does not exist."""
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

    if os.path.exists(prefs_path):
        # Check if the file is blank
        if os.path.getsize(prefs_path) == 0:
            # Write default preferences to the file if it is blank
            with open(prefs_path, 'w') as file:
                json.dump(default_prefs, file, indent=4)
            return default_prefs
        else:
            # Load and return preferences if the file exists and is not blank
            with open(prefs_path, 'r') as file:
                return json.load(file)
    else:
        # Create the prefs.json file with default preferences if it does not exist
        with open(prefs_path, 'w') as file:
            json.dump(default_prefs, file, indent=4)
        return default_prefs

def save_preferences(preferences):
    """Save preferences to the JSON file."""
    with open('/home/underwood/prefs.json', 'w') as file:
        json.dump(preferences, file, indent=4)

def get_location_from_google(wifi_networks):
    """
    Send Wi-Fi networks data to Google's Geolocation API to determine the device's location.
    """
    url = "https://www.googleapis.com/geolocation/v1/geolocate"
    headers = {"Content-Type": "application/json"}
    params = {"key": os.getenv('GOOGLE_API_KEY')}
    data = {"wifiAccessPoints": wifi_networks}

    response = requests.post(url, headers=headers, params=params, json=data)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error: {response.status_code} {response.text}")
        return f"Error: {response.status_code} {response.text}"

def get_location_name(lat, lng):
    """
    Use Google Maps Geocoding API to convert latitude and longitude to location name.
    """
    geocode_url = f"https://maps.googleapis.com/maps/api/geocode/json?latlng={lat},{lng}&key={os.getenv('GOOGLE_API_KEY')}"
    response = requests.get(geocode_url)
    if response.status_code == 200:
        results = response.json().get('results', [])
        if results:
            address_components = results[0].get('address_components', [])
            neighborhood = None
            city = None
            state = None
            for component in address_components:
                if 'sublocality_level_1' in component.get('types', []):
                    city = component.get('long_name')
                elif 'locality' in component.get('types', []):
                    city = component.get('long_name')
                elif 'administrative_area_level_1' in component.get('types', []):
                    state = component.get('long_name')
            return city, state
        else:
            return None, None
    else:
        return None, None

def get_time_of_day(tz):
            
    # Get the current system time
    current_hour = datetime.now(ZoneInfo(tz)).hour

    # Determine the time of day
    if 4 <= current_hour < 12:
        return "morning"
    elif 12 <= current_hour < 17:
        return "afternoon"
    else:
        return "evening"

def remove_last_network_block():
    """Removes the last network block from wpa_supplicant.conf."""
    with open('/etc/wpa_supplicant/wpa_supplicant.conf', 'r') as file:
        lines = file.readlines()

    start_line = None
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].startswith('network={'):
            start_line = i
            break

    if start_line is not None:
        with open('/etc/wpa_supplicant/wpa_supplicant.conf', 'w') as file:
            file.writelines(lines[:start_line])

def scan_wifi(interface='wlan0'):
    """
    Scan for Wi-Fi networks using wpa_cli and extract MAC addresses, signal strengths, and SSIDs.
    """
    wifi_networks = []
    try:
        # Trigger a new scan
        subprocess.run(['sudo', 'wpa_cli', '-i', interface, 'scan'], check=True)

        # Give a little time for scan to complete, this may need to be adjusted
        time.sleep(3)

        # Fetch the scan results
        scan_output = subprocess.check_output(['sudo', 'wpa_cli', '-i', interface, 'scan_results']).decode('utf-8')

        # Parse the scan results
        for line in scan_output.split('\n'):
            parts = line.split()
            if len(parts) >= 5 and parts[0] not in ('bssid', 'BSSID'):
                mac_address = parts[0]
                signal_strength = parts[2]
                ssid = ' '.join(parts[4:])  # SSID can contain spaces
                wifi_networks.append({
                    "macAddress": mac_address,
                    "signalStrength": int(signal_strength),
                    "ssid": ssid
                })
    except subprocess.CalledProcessError as e:
        print(f"Failed to scan for Wi-Fi networks: {e}")
    except Exception as e:
        print(f"An error occurred: {e}")

    return wifi_networks

def configure_wifi(ssid, password):
    """Configure the Wi-Fi connection using wpa_cli, setting the network with the highest priority."""
    
    underwood_listener.send_text("Okay! Give me a few moments, I'm going to try to connect. This may take up to 20 seconds.")

    try:
        # Add a new network and get its network ID
        add_network_output = subprocess.run(['sudo', 'wpa_cli', '-i', 'wlan0', 'add_network'], capture_output=True, text=True)
        network_id = add_network_output.stdout.strip().splitlines()[-1]  # Last line should be the network id

        # Set network SSID and PSK
        subprocess.run(['sudo', 'wpa_cli', '-i', 'wlan0', 'set_network', network_id, 'ssid', f'"{ssid}"'], check=True)
        subprocess.run(['sudo', 'wpa_cli', '-i', 'wlan0', 'set_network', network_id, 'psk', f'"{password}"'], check=True)

        # Determine the highest priority of existing networks
        list_output = subprocess.run(['sudo', 'wpa_cli', '-i', 'wlan0', 'list_networks'], capture_output=True, text=True)
        max_priority = 0
        for line in list_output.stdout.splitlines()[1:]:  # Skip the first line (header)
            fields = line.split()
            if len(fields) >= 4:  # Ensure there are enough fields
                current_priority_output = subprocess.run(['sudo', 'wpa_cli', '-i', 'wlan0', 'get_network', fields[0], 'priority'], capture_output=True, text=True)
                current_priority = int(current_priority_output.stdout.strip())
                if current_priority > max_priority:
                    max_priority = current_priority

        # Set priority of the new network higher than the highest found
        new_priority = max_priority + 1
        subprocess.run(['sudo', 'wpa_cli', '-i', 'wlan0', 'set_network', network_id, 'priority', str(new_priority)], check=True)

        subprocess.run(['sudo', 'wpa_cli', '-i', 'wlan0', 'enable_network', network_id], check=True)

        # Save the configuration to ensure it persists
        subprocess.run(['sudo', 'wpa_cli', '-i', 'wlan0', 'save_config'], check=True)

        # Use reassociate to connect to the best available network
        subprocess.run(['sudo', 'wpa_cli', '-i', 'wlan0', 'reconfigure'], check=True)

        return network_id  # Return the network ID for further management
    except subprocess.CalledProcessError as e:
        print(f"Failed to configure Wi-Fi: {e}")
        return None

def connect_to_wifi(message_queue):

    underwood_listener.clear_queue()

    tz = get_localzone_name()

    time_of_day = get_time_of_day(tz)
    greeting_shown = False
        
    wifi_networks = scan_wifi()
        
    prefs = load_preferences()
    
    if wifi_networks:                
        available_ssids = [network['ssid'] for network in wifi_networks]
    
    while True:

        if (prefs['first_boot'] == True):
            time_of_day = get_time_of_day("America/Chicago")
            if not greeting_shown:
                underwood_listener.send_text("\r")
                underwood_listener.send_text(f"Good {time_of_day}! I'm Mr. Underwood, and I'll be your new personal assistant.")
                underwood_listener.send_text("I can help you keep track of your to-do list by monitoring your Gmail inbox and your Google calendars.")
                underwood_listener.send_text("To get started, I just need a little help getting connected.")
                greeting_shown = True
        
        underwood_listener.send_text("Please type in your (2.4GHz) Wi-Fi network name (and then hit the RETURN key): ")
        
        try:
            raw_data = message_queue.get(timeout=60)
            if raw_data:
                if b'\x7f' in raw_data:  # Check for character 127 (DEL)
                    print("delete")
                    #return
                else:
                    ssid = raw_data.decode('utf-8').strip()
    
                    if ssid not in available_ssids:
                        underwood_listener.send_text(f"I'm so sorry, but I couldn't find a network named '{ssid}'. Would you mind trying that again? ")
                        continue
                
                    underwood_listener.send_text(f"Great! Now, what's the password for '{ssid}'? ")
                    while True:
                    
                        try:
                            raw_data = message_queue.get(timeout=60)                     
                            password = raw_data.decode('utf-8').strip()
                            
                            network_id = configure_wifi(ssid, password)
                            #print(str(subprocess.check_output("iwgetid -r", shell = True)))
                            if network_id is not None:
                                time.sleep(20)  # Wait for connection to establish
                                if ssid in str(subprocess.check_output("iwgetid -r", shell = True)) and underwood_listener.is_online():
                                    underwood_listener.send_text(f"Good news! I've successfully connected to {ssid}.")
                                    
                                    location_response = get_location_from_google(wifi_networks)
                                    if 'location' in location_response:
                                        prefs['lat'] = location_response['location']['lat']
                                        prefs['lng'] = location_response['location']['lng']
                                        city, state = get_location_name(prefs['lat'], prefs['lng'])
                                        prefs['city'] = city if city else 'Chicago'
                                        prefs['state'] = state if state else 'Illinois'
                                        save_preferences(prefs)
                                    else:
                                        print("Missing location data")

                                    get_credentials(message_queue)
                                    
                                    prefs = load_preferences()
                                    prefs['first_boot'] = False
                                    save_preferences(prefs)
 
                                    return  # Exit the password loop on successful connection
                                else:
                                    print(password)
                                    underwood_listener.send_text(f"I'm so sorry, but I wasn't able to connect to '{ssid}'. Would you mind checking your password and trying again? ")
                                    # Remove the network if connection fails
                                    subprocess.run(['sudo', 'wpa_cli', '-i', 'wlan0', 'remove_network', network_id], check=True)
                                    subprocess.run(['sudo', 'wpa_cli', '-i', 'wlan0', 'save_config'], check=True)
                                    subprocess.run(['sudo', 'wpa_cli', '-i', 'wlan0', 'enable_network', 'all'], check=True)
                                    subprocess.run(['sudo', 'wpa_cli', '-i', 'wlan0', 'reconfigure'], check=True)
                                    # Instead of breaking, it loops back to ask for the password again without repeating the "Great! Now, what's the password?" line.
                            else:
                                underwood_listener.send_text(f"I'm so sorry, but I wasn't able to connect to '{ssid}'. Please try again.")
            
                        except Exception as e:
                            print(f"An error occurred: {str(e)}")
                            return

        except Empty:
            underwood_listener.send_text("I'm sorry, I didn't catch that. If you want to try connecting to WI-Fi again, please hit the RELOC key and select it from the menu!")
            return


############## GOOGLE OAUTH ##############

# Gmail API setup
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly',
          'https://www.googleapis.com/auth/calendar.readonly',
          'https://www.googleapis.com/auth/userinfo.profile']

oauth_url = None  # Global variable to hold the OAuth URL

class CallbackHandler(BaseHTTPRequestHandler):
    authorization_code = None
    error_message = None  # To handle different types of errors

    def do_GET(self):
        global oauth_url
        parsed_url = urlparse(self.path)
        if parsed_url.path == "/":  # Redirect base path to OAuth URL
            if oauth_url:
                self.send_response(302)
                self.send_header('Location', oauth_url)
                self.end_headers()
            else:
                self.send_error(503, "Service Unavailable: OAuth URL not yet available")
        else:
            query_params = parse_qs(parsed_url.query)
            CallbackHandler.authorization_code = query_params.get('code', [None])[0]
            if CallbackHandler.authorization_code:
                self.send_response(200)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                response_html = """
                <html>
                    <head>
                        <title>Authorization Successful</title>
                        <meta name="viewport" content="width=device-width, initial-scale=1">
                        <style>
                            body { font-family: 'Courier', monospace; padding: 20px; margin: 0; background-color: #f4f4f9; color: #333; }
                            h1 { font-size: 1.5em; color: #444; }
                            p { font-size: 1em; }
                            .container { width: 90%; max-width: 600px; margin: auto; background: white; padding: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
                        </style>
                    </head>
                    <body>
                        <div class="container">
                            <h1>Authorization confirmed!<br><br>You can now close this window.</h1>
                            <p>If you change your mind in the future, head to your <a href="https://myaccount.google.com/connections">Google Account</a> and look for 'Underwood' to revoke access.</p>
                            <p>Reach out to <a href="mailto:josh@thingswemake.com">josh@thingswemake.com</a> with any questions!</p>
                        </div>
                    </body>
                </html>
                """
                self.wfile.write(response_html.encode('utf-8'))
            else:
                self.send_response(400)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                response_html = """
                <html>
                    <head>
                        <title>Authorization Failed</title>
                        <meta name="viewport" content="width=device-width, initial-scale=1">
                        <style>
                            body { font-family: 'Courier', monospace; padding: 20px; margin: 0; background-color: #f4f4f9; color: #333; }
                            h1 { font-size: 1.5em; color: #d33; }
                            p { font-size: 1em; }
                            .container { width: 90%; max-width: 600px; margin: auto; background: white; padding: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
                        </style>
                    </head>
                    <body>
                        <div class="container">
                            <h1>I'm sorry, but you'll need to authorize access in order to continue.<br><br><a href="https://login.underwood.today/">Please try the process again.</a></h1>
                            <p>You can always revoke access later by heading to your <a href="https://myaccount.google.com/connections">Google Account</a>.</p>
                            <p>Reach out to <a href="mailto:josh@thingswemake.com">josh@thingswemake.com</a> with any questions!</p>
                        </div>
                    </body>
                </html>
                """
                self.wfile.write(response_html.encode('utf-8'))

def get_credentials(message_queue):
    global oauth_url
    credentials = None
    
#     credential_path = "/home/underwood/underwood-417620-d00783028138.json"
#     os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = credential_path
    
    if os.path.exists('/home/underwood/token.pickle'):
        with open('/home/underwood/token.pickle', 'rb') as token:
            credentials = pickle.load(token)
    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            # Save the refreshed credentials
            with open('token.pickle', 'wb') as token:
                pickle.dump(credentials, token)
        else:
            # Start a simple HTTP server to handle the redirect
            port = 8080
            handler = CallbackHandler
            httpd = socketserver.TCPServer(("", port), handler)
            # print(f"Local server is running on port {port}")

            # Start Cloudflare tunnel using subprocess
            cloudflared_process = subprocess.Popen(['sudo', '-u' ,'underwood', 'cloudflared', 'tunnel', 'run', '--url', 'localhost:8080', '9dacf679-da50-4323-9ce2-bf7388380d6c'])
            # print("Cloudflare tunnel started")

            # Assuming your Cloudflare tunnel points to localhost:8080
            redirect_uri = 'https://login.underwood.today/oauth2callback'
            # print(f"Redirect URI: {redirect_uri}")
            flow = InstalledAppFlow.from_client_secrets_file('/home/underwood/client_secret.json', SCOPES, redirect_uri=redirect_uri)

            oauth_url, _ = flow.authorization_url(access_type='offline', prompt='consent')
            
            # Create a thread that runs my_function
            auth_instruct_thread = threading.Thread(target=auth_instructions)
            
            # Start the thread
            auth_instruct_thread.start()
            
            timeout = 120  # Timeout in seconds (e.g., 2 minutes)
            start_time = time.time()

            try:
                while CallbackHandler.authorization_code is None and not CallbackHandler.error_message:
                    httpd.handle_request()
                    
                    if time.time() - start_time > timeout:
                        underwood_listener.send_text("Oh dear, our session has timed out. Would you mind trying again?")
                        start_time = time.time()  # Reset timer and allow for another attempt
            finally:
                httpd.server_close()
                cloudflared_process.terminate()
                auth_instruct_thread.join()
                # print("HTTP server and tunnel closed.")
    
            if CallbackHandler.authorization_code:
                flow.fetch_token(code=CallbackHandler.authorization_code)
                credentials = flow.credentials
                with open('token.pickle', 'wb') as token:
                    pickle.dump(credentials, token)
                set_name(credentials)
                underwood_listener.send_text("Hooray! You've successfully connected your Google account.")
                underwood_listener.send_text("You can hit the EXPR key at any time to get your agenda, or hit the RELOC key for settings.")        
                schedule_agenda(message_queue)

    return credentials

def auth_instructions():
    prefs = load_preferences()

    if prefs['fname']:
        underwood_listener.send_text(f"It looks like I need to get re-connected to your Gmail and Google Calendar! To make that happen, please visit this link on your phone: https://login.underwood.today")
    else:
        underwood_listener.send_text(f"Now, in order for me to provide your agenda, I'll need to get connected to your Gmail and Google Calendar! To make that happen, please visit this link on your phone: https://login.underwood.today")

        underwood_listener.send_text("(Note: while this app is awaiting Google approval, you may see a message that says 'Google hasn't verified this app.' You'll need to tap 'Advanced,' then 'Go to underwood.today (unsafe),' then select each checkbox and hit 'Continue.' Spoiler alert: it's not unsafe, just pending review. I apologize for the extra steps!)")

def set_name(credentials):

    prefs = load_preferences()

    #Build the people service
    people_service = build('people', 'v1', credentials=credentials, cache_discovery=False)
    
    # Request to get the user's names
    results = people_service.people().get(resourceName='people/me', personFields='names').execute()
    names = results.get('names', [])
    
    if names:
        name = names[0]  # Assuming the first name object is the primary name
        prefs['fname'] = name.get('givenName', 'Andrew')
        prefs['lname'] = name.get('familyName')
        save_preferences(prefs)
        
        
############## LAUNCHER ##############

def main():
    
    connect_to_wifi(underwood_listener.message_queue)
    
if __name__ == "__main__":
    main()