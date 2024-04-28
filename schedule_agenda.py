############## EXTERNAL FUNCTIONS ##############

import underwood_listener

############## DEPENDENCIES ##############

import json
from typing import List
import recognizers_suite as Recognizers
from recognizers_suite import Culture, ModelResult
from crontab import CronTab
from queue import Queue, Empty
from datetime import datetime
import time
from dotenv import load_dotenv
load_dotenv()

def schedule_agenda(message_queue):
    """Manage the scheduling of the agenda generation with an overall timeout."""
    cron = CronTab(user='root')
    job_comment = 'generate_agenda_job'
    jobs = list(cron.find_comment(job_comment))

    underwood_listener.clear_queue()

    if jobs:
        job = jobs[0]
        underwood_listener.send_text(f"You're currently set up to receive your agenda at {job.description(use_24hour_time_format=False).lower()}.")
        underwood_listener.send_text("Type 'delete' to remove the schedule or 'change' to update the time, and then hit the RETURN key. Or, hit the BACKSPACE key to cancel.")
    else:
        underwood_listener.send_text("Would you like me to print your agenda at a certain time each day? Type 'set' and then hit the RETURN key to start the scheduler, or hit the BACKSPACE key to cancel.")

    timeout_duration = 60  # seconds
    start_time = time.time()  # Record the start time

    while True:
        try:
            elapsed_time = time.time() - start_time
            remaining_time = timeout_duration - elapsed_time
            if remaining_time <= 0:
                underwood_listener.send_text("I'm sorry, I didn't quite catch that. Please try scheduling your agenda again.")
                return

            raw_data = message_queue.get(timeout=remaining_time)  # Adjust timeout based on elapsed time
            if raw_data:
                if b'\x7f' in raw_data:  # Check for DEL character
                    underwood_listener.send_text("Your request to adjust your schedule has been canceled.")
                    return
                else:
                    choice = raw_data.decode('utf-8').strip().lower()
                    try:
                        if choice == 'delete':
                            job.delete()
                            cron.write()
                            underwood_listener.send_text("I've deleted your schedule! You can always set up another one by hitting the RELOC key.")
                            return
                        elif choice in ['change', 'set']:
                            return handle_time_change(choice, cron, jobs, job_comment, message_queue, start_time, timeout_duration)
                    except NameError:
                        underwood_listener.send_text("I'm sorry, I didn't quite catch that. Please try entering your choice again.")
                    else:
                        underwood_listener.send_text("I didn't quite catch that. Please type 'delete', 'change', or 'set', followed by the RETURN key, or hit the BACKSPACE key to cancel.")
        except Empty:
            underwood_listener.send_text("I'm sorry, I didn't quite catch that. Please try entering your choice again.")

def handle_time_change(choice, cron, jobs, job_comment, message_queue, start_time, timeout_duration):
    """Handles the user's request to change or set the schedule with a timeout."""
    job = None
    if jobs and choice == 'change':
        job = jobs[0]
    elif choice == 'set':
        job = cron.new(command='sudo -E /usr/bin/python /home/underwood/generate_agenda.py', comment=job_comment)

    while True:
        elapsed_time = time.time() - start_time
        remaining_time = timeout_duration - elapsed_time
        if remaining_time <= 0:
            underwood_listener.send_text("I'm sorry, I didn't quite catch that. Please try scheduling your agenda again.")
            return

        underwood_listener.send_text("What time would you like to receive your daily agenda? (e.g., '4:35 pm')")
        try:
            time_data = message_queue.get(timeout=remaining_time)
            if time_data:
                underwood_listener.send_text("Give me a few moments to set up your schedule.")
                new_time_str = time_data.decode('utf-8').strip()
                new_time = parse_time_with_recognizer(new_time_str, Culture.English)
                if new_time:
                    hour = new_time.hour
                    minute = new_time.minute
                    job.clear()
                    job.minute.on(minute)
                    job.hour.on(hour)
                    cron.write()
                    underwood_listener.send_text(f"Scheduled! You'll receive your daily agenda at {new_time.strftime('%-I:%M %p')}.")
                    return
                else:
                    underwood_listener.send_text("I didn't quite catch that. Please try again with a format like '4:35 pm'.")
            else:
                underwood_listener.send_text("I'm sorry, I didn't quite catch that. Please try again.")
        except Empty:
            underwood_listener.send_text("I'm sorry, I didn't quite catch that. Please try scheduling your agenda again.")
            return

def parse_time_with_recognizer(user_input: str, culture: str):
    """Use Microsoft's Recognizers to parse a natural language time input into a time object."""
    results = Recognizers.recognize_datetime(user_input, culture)
    # We expect 'results' to be a list of ModelResult instances.

    # Filter results to find the first time entry
    for result in results:
        if result.type_name == 'datetimeV2.time':
            # Extract the first value from the values list, which should contain the time
            if result.resolution and 'values' in result.resolution:
                time_values = result.resolution['values']
                if time_values:
                    time_value = datetime.strptime(time_values[0]['value'], "%H:%M:%S")
                    return time_value
    return None

############## LAUNCHER ##############

def main():
    schedule_agenda()
    
if __name__ == "__main__":
    main()