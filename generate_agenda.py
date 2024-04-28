############## EXTERNAL FUNCTIONS ##############

import underwood_listener
import get_connected

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
from dateutil import parser
from dateutil.tz import tzlocal
import pytz
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
from textwrap import fill
import emoji

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

prefs = load_preferences()

def custom_translate(text):
    # Create a translation table for specific characters you want to replace
    translation_table = str.maketrans({
        '[': '(',
        ']': ')'
    })
    text = emoji.replace_emoji(text, replace=' ')
    text = text.translate(translation_table)
    text = text.replace('  ', ' ')
    return text

def get_forecast_url():
    """Get the forecast URL from the National Weather Service API, adjusting lat/lng granularity."""
    prefs = load_preferences()

    try:
        # Get lat and lng from preferences or default to downtown Chicago
        lat = prefs.get('lat', 41.8781)
        lng = prefs.get('lng', -87.6298)

        lat, lng = round(lat, 4), round(lng, 4)
        point_url = f"https://api.weather.gov/points/{lat},{lng}"
        response = requests.get(point_url)
        response.raise_for_status()  # Raises an HTTPError for bad responses
        response_data = response.json()
        forecast_url = response_data.get('properties', {}).get('forecast')

        if not forecast_url:
            raise ValueError("Forecast URL not found in the response.")
        
        return forecast_url
    except (requests.RequestException, ValueError) as e:
        print(f"Error retrieving forecast URL: {e}")
        return None

def get_forecast():
    """Get forecasts for the top 3 periods, regardless of their specific names."""
    forecast_url = get_forecast_url()
    if not forecast_url:
        return "Forecast is currently unavailable."

    try:
        response = requests.get(forecast_url)
        response.raise_for_status()  # Ensure we got a good response
        forecast_data = response.json()
        periods = forecast_data.get('properties', {}).get('periods', [])

        if not periods:
            return "No forecast data available."

        top_forecasts = periods[:3]  # Get the top 3 periods
        forecasts = []
        for period in top_forecasts:
            forecasts.append({
                'name': period.get('name'),
                'detailedForecast': period.get('detailedForecast')
            })
        
        forecast_str = "\n".join(f"{forecast['name']}: {forecast['detailedForecast']}" for forecast in forecasts)
        return forecast_str
    except requests.RequestException as e:
        print(f"Error retrieving forecast: {e}")
        return "Forecast unavailable."

def get_local_news():

    base_url = "https://api.bing.microsoft.com/v7.0/news/search"
    headers = {"Ocp-Apim-Subscription-Key": os.getenv('BING_KEY')}
    params = {
        "q": f"{prefs['city']} AND \"{prefs['state']}\" AND (events OR event OR today OR weekend OR traffic OR weather) -police -crime -murder -shot -killed -sports -politics -fire -injured -arrested",
        "count": 10,
        "mkt": "en-US",
        "safeSearch": "Strict",
        "freshness": "Day"
    }

    response = requests.get(base_url, headers=headers, params=params)

    if response.status_code == 200:
        news_items = response.json().get('value', [])
        news_str = ""
        for i, item in enumerate(news_items, start=1):
            news_str += f"{item.get('name')}: {item.get('description')}\n"
    
        return(news_str)

def generate_agenda(message_queue):

    prefs = underwood_listener.load_preferences()

    # Check if we are online
    if not underwood_listener.is_online():
        # Attempt to reconnect or alert the user
        get_connected.connect_to_wifi(message_queue)
    else:

        credentials = None
        if os.path.exists('/home/underwood/token.pickle'):
            with open('/home/underwood/token.pickle', 'rb') as token:
                credentials = pickle.load(token)
        if not credentials or not credentials.valid:
            if credentials and credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
                # Save the refreshed credentials
                with open('/home/underwood/token.pickle', 'wb') as token:
                    pickle.dump(credentials, token)
            else:
                credentials = get_connected.get_credentials(message_queue)
            
        service = build('gmail', 'v1', credentials=credentials)
        
        # Fetch emails from the past 24 hours
        yesterday = datetime.now() - timedelta(days=1)
        query = f'label:inbox after:{yesterday.strftime("%Y/%m/%d")} before:{datetime.now().strftime("%Y/%m/%d")}'
        results = service.users().messages().list(userId='me', q=query).execute()
        messages = results.get('messages', [])
        
        emails = []
        for message in messages:
            msg = service.users().messages().get(userId='me', id=message['id'], format='metadata').execute()
            headers = msg['payload']['headers']
            subject = next(header['value'] for header in headers if header['name'] == 'Subject')
            sender = next((header['value'] for header in headers if header['name'] == 'From'), 'Unknown Sender')
            date_str = next((header['value'] for header in headers if header['name'] == 'Date'), None)
        
            if date_str:
                # Parse the date string and convert it to local timezone
                date_received = parser.parse(date_str)
                local_date = date_received.astimezone(tzlocal())
                date_display = local_date.strftime("%A, %d %B %Y %H:%M:%S %Z")
            else:
                date_display = 'No Date'
            snippet = msg.get('snippet', '')
            emails.append(f"Sender: {sender}, Subject: {subject}, Date Received: {date_display}, Preview: {snippet}")
        
        # Build the Calendar service
        calendar_service = build('calendar', 'v3', credentials=credentials)
        
        # Calendar functionality to fetch events for the next 7 days
        start_time = datetime.utcnow().isoformat() + 'Z'  # 'Z' indicates UTC time
        end_time = (datetime.utcnow() + timedelta(days=7)).isoformat() + 'Z'
        
        # Function to fetch events
        def fetch_events(calendar_id):
            events_result = calendar_service.events().list(
                calendarId=calendar_id,
                timeMin=start_time,
                timeMax=end_time,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            return events_result.get('items', [])
        
        # Fetch events from the primary calendar
        primary_events = fetch_events('primary')
        
        # Fetch events from the additional calendar
        additional_calendar_id = '6lqpbv8647igscie1ictda2c57nigmcn@import.calendar.google.com' # public US holidays & observances
        birthday_calendar_id = 'addressbook#contacts@group.v.calendar.google.com' # public US holidays & observances
        additional_events = fetch_events(additional_calendar_id)
        birthdays = fetch_events(birthday_calendar_id)
        
        # Combine events from all calendars
        all_events = primary_events + additional_events + birthdays
        
        cal_list = []
        
        for event in all_events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            cal_list.append(f"Event: {event['summary']}, Start: {start}")
            
        if prefs['fname']:
            name_prompt = f"I'm {prefs['fname']}. "
        else:
            name_prompt = "" 
        
        # Get today's date
        today = datetime.now().strftime("%A, %B %d, %Y, and it's around %-I %p")
        
        email_details = "\n".join(emails)  # Assuming `emails` contains the list of email details
        cal_details = "\n".join(cal_list)
        
        # Get local weather & news highlights
        forecast_str = get_forecast()
        news_str = get_local_news()
        
        user_message = f"Today is {today}. {name_prompt}You're my executive assistant Mr. Underwood. You're a little quirky and goofy. Write me a quick, concise, chipper, friendly note updating me on my agenda. Don't offer any follow-up help. Avoid using non-ASCII characters. Include the date. Be concise - time is money - but include a motivational quote. Mention any important emails from the below list (ignore promotional emails, and focus on things I need to deal with), identify any upcoming holidays, mention any upcoming events from my calendar, and weave in any relevant highlights from the forecast and or/local news, if they seem important and worthy of my busy schedule, from any provided below (ignore any blank sections):\n\nEMAILS:\n\n{email_details}\n\nCALENDAR EVENTS:\n\n{cal_details}\n\n WEATHER:\n{forecast_str}\n\n {prefs['city'].upper()} NEWS:\n{news_str}"
            
        # Initialize the OpenAI client
        client = OpenAI(
            api_key = os.getenv('OPENAI_API_KEY')
        )
        
        # Prepare the chat messages
        messages = [
            {"role": "system", "content": "You are my helpful executive assistant."},
            {"role": "user", "content": user_message}
        ]
        
        # Send request to OpenAI API using chat completions
        response = client.chat.completions.create(
          model="gpt-4-turbo",  # Use the appropriate model for your use case
          messages=messages
        )
                
        underwood_listener.send_text(custom_translate(response.choices[0].message.content))

############## LAUNCHER ##############

def main():
    generate_agenda(underwood_listener.message_queue)
    
if __name__ == "__main__":
    main()