from pathlib import Path
from datetime import datetime, timedelta

import toml
from decouple import config
from googleapiclient import discovery
from google.oauth2.service_account import Credentials
from slugify import slugify


PHOTO_URL = "https://2019.pythonbrasil.org.br/assets/images/fotos/{}.jpeg"


# Build Google API Client
credentials = Credentials.from_service_account_file(
    config("GOOGLE_API_CREDENTIALS"),
    scopes=["https://www.googleapis.com/auth/calendar"],
)
client = discovery.build("calendar", "v3", credentials=credentials)

# Search for calendar related to this year's Python Brasil.
# Create new one if not found.
today = datetime.now()
calendar_name = f"Python Brasil {today.year} - Grade"
print(f"📆  {calendar_name}\n")


for calendar in client.calendarList().list().execute()["items"]:
    if calendar["summary"] == calendar_name:
        print("Calendar found")
        break
else:
    print("Calendar not found, creating new one")
    calendar = client.calendars().insert(body={"summary": calendar_name}).execute()

print("Calendar ID:", calendar["id"])

# Setup read-only access for public user.
rule = {"scope": {"type": "default"}, "role": "reader"}
acl = client.acl().insert(calendarId=calendar["id"], body=rule).execute()
print("ACL created, id:", acl["id"])

events = []
page_token = None
while True:
    response = (
        client.events().list(calendarId=calendar["id"], pageToken=page_token).execute()
    )
    events.extend(response["items"])

    page_token = response.get("nextPageToken")
    if not page_token:
        break

# Remove any existent events.
if len(events) > 0:
    print(f"Reseting calendar, removing {len(events)} events found")

    batch = client.new_batch_http_request()
    for event in events:
        batch.add(
            client.events().delete(
                calendarId=calendar["id"], eventId=event["id"], sendUpdates="all"
            )
        )

    batch.execute()

# Search and read for TOML files. Aggregate the ones that contains `slot` configuration.
slots = []
conferences = Path(config("CONFERENCES_PATH", "conferencias"))
for config_file in conferences.glob("**/*.toml"):
    print("Reading config file:", config_file)
    with config_file.open() as fp:
        config = toml.load(fp)
        slots.extend(config.get("slot", []))

# Create Calendar Event for each slot found on configuration files
print("Total events found:", len(slots))
batch = client.new_batch_http_request()
for slot in slots:
    start_at = slot["start_at"]
    if not start_at.year == today.year:
        continue
    duration = slot["duration"]
    end_at = start_at + timedelta(minutes=duration)

    author = slot.get("author", "")
    photo_url = slot.get("photo_url", "")
    if not photo_url and author:
        photo_url = PHOTO_URL.format(slugify(author, separator="_"))

    title = slot["name"]
    description = slot.get("description", "")
    location = slot.get("room", "")
    event_type = slot.get("type", "")
    category = slot.get("category", "")
    discord_channel = slot.get("discord_channel", "")
    youtube_channel = slot.get("youtube_channel", "")

    event = {
        "summary": title,
        "description": description,
        "start": {"dateTime": start_at.isoformat(), "timeZone": "America/Sao_Paulo"},
        "end": {"dateTime": end_at.isoformat(), "timeZone": "America/Sao_Paulo"},
        "location": location,
        "creator": {
            "displayName": f"Python Brasil {today.year}",
            "email": "eventos@python.org.br",
        },
        "extendedProperties": {
            "private": {
                "title": title,
                "author": author,
                "category": category,
                "type": event_type,
                "photo_url": photo_url,
                "discord_channel": discord_channel,
                "youtube_channel": youtube_channel,
            }
        },
    }
    print("Creating event:", title)
    batch.add(client.events().insert(calendarId=calendar["id"], body=event))

batch.execute()

print("Calendar ID:", calendar["id"])
print(f"Calendar UI: https://calendar.google.com/calendar/embed?src={calendar['id']}")
