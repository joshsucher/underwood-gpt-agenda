#!/usr/bin/env python3

############## DEPENDENCIES ##############

#SYS

from datetime import datetime, timedelta
import time
import os
import serial
import sys
import subprocess
from crontab import CronTab
from threading import Thread
from queue import Queue, Empty
from dotenv import load_dotenv
load_dotenv()

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
import textwrap
import emoji
from anyascii import anyascii

############## EXTERNAL FUNCTIONS ##############

import generate_agenda
import get_connected
import reset_system
import schedule_agenda

############## CONNECT TO ARDUINO ##############

arduino = serial.Serial('/dev/ttyACM0', 9600)
time.sleep(1 / 5)

############## SEND & RECEIVE TEXT ##############

global message_queue
message_queue = Queue()

def send_text(text):
    """Send the text to the typewriter, ensuring each line does not exceed 55 characters."""
    # Wrap the text and split into lines
    send_character(chr(30)) # control character - start tx
    
    textGrafs = text.splitlines()

    for graf in textGrafs:
        lines = textwrap.wrap(graf, width=55, break_long_words=True, break_on_hyphens=True)
        for line in lines:
            line = anyascii(line)
            for character in line:
                send_character(character)
            # Send carriage return to start a new line
            send_character('\r')
            time.sleep(1.2)
        send_character('\r')
    send_character(chr(31)) # control character - end tx

def send_character(character):
    # Assuming an average typing speed, we introduce a slight delay
    arduino.write(character.encode())
    time.sleep(0.2)  # Delay to mimic around 200 characters per minute

def receive_typed_text():
    """Continuously read typed text from the Arduino."""
    while True:
        if arduino.in_waiting > 0:
            raw_data = arduino.readline()
            message_queue.put(raw_data)
            
def process_messages():
    """Process messages from the queue indefinitely."""

    #send_text("Hi there! Just give me a few moments to get ready.")

    #time.sleep(5)
    
    if not is_online():
        get_connected.connect_to_wifi(message_queue)
    else:
        send_text("\r")
        send_text("All set! You can hit the EXPR key at any time to get your agenda, or hit the RELOC key for settings.")        
        
    while True:
        try:
            raw_data = message_queue.get()
            if raw_data:
                if b'\x15' in raw_data:  # NAK: Open settings menu
                    settings_menu()
                elif b'\x16' in raw_data:  # SYN: Prepare agenda
                    send_text("I'm preparing your agenda. Please hold!")
                    generate_agenda.generate_agenda(message_queue)
                elif b'\x1a' in raw_data:  # SUB: Reset Wi-Fi
                    send_text("I'm resetting Wi-Fi to default. Please hold!")
                    reset_wpa()
        except Empty:
            print("No input detected, please try again.")
        except Exception as e:
            print(f"An error occurred: {str(e)}")
            continue  # Maintain the loop unless a shutdown is initiated

def clear_queue():
    try:
        while True:  # Keep running until an exception is raised
            message_queue.get_nowait()  # Attempt to get item from queue without blocking
    except Empty:
        pass  # When queue is empty, an Empty exception is raised

############## ONLINE ##############

def is_online(host="8.8.8.8", count=1, timeout=3):
    """
    Check if the device is online by pinging a known server.
    """
    try:
        subprocess.check_output(['ping', '-c', str(count), '-W', str(timeout), host], stderr=subprocess.STDOUT)
        return True
    except subprocess.CalledProcessError:
        return False

def reset_wpa():
    """
    Completely overwrite the wpa_supplicant.conf file with a new network configuration.
    """
    wpa_supplicant_conf_path = '/etc/wpa_supplicant/wpa_supplicant.conf'

    try:
        # Prepare the complete new configuration content
        new_config_content = f"""
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
country=US

network={{
    ssid="Underwood"
    psk="praxis35"
    key_mgmt=WPA-PSK
}}
"""
        # Open the wpa_supplicant configuration file in write mode to overwrite
        with open(wpa_supplicant_conf_path, 'w') as file:
            file.write(new_config_content)

        # Trigger reconfiguration to apply changes
        subprocess.run(['sudo', 'wpa_cli', '-i', 'wlan0', 'reconfigure'], check=True)
        send_text("Wi-Fi has been reset to default. Please hit the RELOC key to add a new network.")
        return
    except Exception as e:
        print(f"An error occurred while overwriting wpa_supplicant.conf: {str(e)}")

############## PREFS ##############

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

def settings_menu():
    """Display the main menu and handle user choices."""
    prefs = load_preferences()

    clear_queue()
    
    send_text("\r")
    send_text("Here are some options. Type the number of your selection and hit the RETURN key to proceed (or hit the BACKSPACE key to cancel):")
    send_text("\r")
    send_text("1. Print your agenda now")
    send_text("2. Schedule a recurring time to print your agenda")
    send_text("3. Connect to a new Wi-Fi network")
    send_text("4. Learn more about this project")
    send_text("5. Disconnect & reset the system")
    send_text("\r")
    awaiting_response = True
    
    while True:
        try:
            raw_data = message_queue.get(timeout=30)  # 30 seconds timeout for user to respond
            if raw_data:
                if b'\x7f' in raw_data:  # Check for character 127 (DEL)
                    send_text("Your last action has been canceled!")
                    return
                else:
                    choice = raw_data.decode('utf-8').strip()
                    print(choice)
                    # Process the choice as previously done
                    if choice == '1':
                        send_text("I'm preparing your agenda. Please hold!")    
                        generate_agenda.generate_agenda(message_queue)
                    elif choice == '2':
                        schedule_agenda.schedule_agenda(message_queue)
                    elif choice == '3':
                        get_connected.connect_to_wifi(message_queue)
                    elif choice == '4':
                        send_text("Mr. Underwood uses GPT-4 and various Google APIs to summarize your Gmail inbox and calendar into a daily agenda. Data is processed by a Raspberry Pi Zero 2 W, which controls the typewriter via an Arduino Nano Every.")
                        send_text("Data is sent to the GPT-4 API for synthesis, but is not retained, accessible, or saved on OpenAI's servers or on-device once each agenda has been generated.")
                        send_text("GPT-4 analyzes subject lines and brief previews from emails received in your inbox over the past 24 hours, as well as calendar events for the next 7 days. Geolocation data is sent to Bing News and NWS APIs for local news and weather.")            
                        send_text("When you're not getting an agenda, you can use the typewriter as one normally would (if this were 1983). The original manual, included in the case, describes all of its functionality. Note that the 'KB I/II' switch brings up special characters, and your agenda will look weird unless you keep it set to 'KB I'. The '10/12/15' switch refers to pitch; Mr. Underwood expects 10 cpi.")            
                        send_text("For questions, issues, concerns or feature requests, reach out to Josh Sucher at *josh@thingswemake.com*.")
                        send_text("To read more about this project, head to *https://underwood.today*.")
                    elif choice == '5':
                        reset_system.reset_system(message_queue)
                    else:
                        send_text("I'm sorry, I didn't catch that. Please try again!")
                #return
        except Empty:
            send_text("I'm sorry, I didn't catch that. I'll go ahead and close the menu, but please feel free to try again!")
            return  # Break the loop if no input received
        except Exception as e:
            print(f"An error occurred: {str(e)}")
            return  # Exit on other exceptions

############## LAUNCHER ##############

def main():
    
    # Setup threads and resources
    receive_thread = Thread(target=receive_typed_text, daemon=True)
    process_thread = Thread(target=process_messages, daemon=True)

    receive_thread.start()
    process_thread.start()

    try:
        # Wait indefinitely for threads to complete (they won't if daemon)
        receive_thread.join()
        process_thread.join()
    except KeyboardInterrupt:
        print("Interrupt received, exiting...")
    finally:
        shutdown()

def shutdown():
    """Close all resources."""
    print("Shutting down. Closing serial connection...")
    arduino.close()
    print("Serial connection closed.")

if __name__ == "__main__":
    main()
