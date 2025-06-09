import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

# Load environment variables
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("DATABASE_ID")  # Active Database
DATABASE_ID_COMPLETED = os.getenv("DATABASE_ID_COMPLETED")  # Completed Database
SONARR_API_KEY = os.getenv("SONARR_API_KEY")
SONARR_URL = os.getenv("SONARR_URL")
RADARR_API_KEY = os.getenv("RADARR_API_KEY")
RADARR_URL = os.getenv("RADARR_URL")
ROOT_FOLDER_TV = os.getenv("ROOT_FOLDER_TV")
ROOT_FOLDER_MOVIE = os.getenv("ROOT_FOLDER_MOVIE")

# API headers
notion_headers = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json"
}
sonarr_headers = {
    "X-Api-Key": SONARR_API_KEY,
    "Content-Type": "application/json"
}
radarr_headers = {
    "X-Api-Key": RADARR_API_KEY,
    "Content-Type": "application/json"
}

# === Notion query ===
def query_notion():
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    print(f"🔍 Querying Notion database: {DATABASE_ID}")
    response = requests.post(url, headers=notion_headers)
    print(f"🔎 Raw Notion response status: {response.status_code}")
    print(f"🔎 Raw Notion response body: {response.text}")  # Print full response for debugging
    response.raise_for_status()
    return response.json()["results"]

def archive_notion_page(page_id):
    url = f"https://api.notion.com/v1/pages/{page_id}"
    data = {
        "archived": True
    }
    response = requests.patch(url, headers=notion_headers, json=data)
    if response.status_code == 200:
        print(f"🗑️ Archived Notion page {page_id}")
    else:
        print(f"❌ Failed to archive Notion page {page_id}: {response.status_code}, {response.text}")

def copy_to_completed_database(title, notes, tvdb_id=None, tmdb_id=None):
    properties = {
        "Raw Title": {"title": [{"text": {"content": title}}]},
        "Notes": {"multi_select": [{"name": note} for note in notes]},
        "Confirmed": {"checkbox": True},
        "Added": {"checkbox": True},
        "System Response": {"rich_text": [{"text": {"content": "✅ Added Successfully"}}]}
    }
    
    if tvdb_id is not None:
        properties["TVDB ID"] = {"number": tvdb_id}
    if tmdb_id is not None:
        properties["TMDB ID"] = {"number": tmdb_id}

    payload = {
        "parent": {"database_id": DATABASE_ID_COMPLETED},
        "properties": properties
    }

    url = "https://api.notion.com/v1/pages"
    response = requests.post(url, headers=notion_headers, json=payload)
    if response.status_code == 200:
        print(f"✅ Copied '{title}' to Completed Database.")
    else:
        print(f"❌ Failed to copy '{title}': {response.status_code}, {response.text}")

# === Sonarr ===
def lookup_tv_show(tvdb_id):
    url = f"{SONARR_URL}/api/v3/series/lookup?term=tvdb:{tvdb_id}"
    response = requests.get(url, headers=sonarr_headers)
    if response.status_code != 200:
        print(f"❌ Failed to lookup TVDB ID {tvdb_id}: {response.status_code}")
        return None
    results = response.json()
    return results[0] if results else None

def add_tv_to_sonarr(show):
    payload = {
        "tvdbId": show["tvdbId"],
        "title": show["title"],
        "titleSlug": show["titleSlug"],
        "images": show.get("images", []),
        "seasons": show.get("seasons", []),
        "qualityProfileId": 1,
        "rootFolderPath": ROOT_FOLDER_TV,
        "monitored": True,
        "addOptions": {
            "monitor": "all",
            "searchForMissingEpisodes": True
        }
    }
    url = f"{SONARR_URL}/api/v3/series"
    response = requests.post(url, headers=sonarr_headers, json=payload)
    if response.status_code != 201:
        print(f"❌ Failed to add to Sonarr: {show['title']}")
        print(response.text)
        return False
    print(f"✅ Added to Sonarr: {show['title']}")
    return True

# === Radarr ===
def lookup_movie(tmdb_id):
    url = f"{RADARR_URL}/api/v3/movie/lookup?term=tmdb:{tmdb_id}"
    response = requests.get(url, headers=radarr_headers)
    if response.status_code != 200:
        print(f"❌ Failed to lookup TMDB ID {tmdb_id}: {response.status_code}")
        return None
    results = response.json()
    return results[0] if results else None

def add_movie_to_radarr(movie):
    payload = {
        "tmdbId": movie["tmdbId"],
        "title": movie["title"],
        "titleSlug": movie["titleSlug"],
        "images": movie.get("images", []),
        "qualityProfileId": 1,
        "rootFolderPath": ROOT_FOLDER_MOVIE,
        "monitored": True,
        "addOptions": {
            "searchForMovie": True
        }
    }
    url = f"{RADARR_URL}/api/v3/movie"
    response = requests.post(url, headers=radarr_headers, json=payload)
    if response.status_code != 201:
        print(f"❌ Failed to add to Radarr: {movie['title']}")
        print(response.text)
        return False
    print(f"✅ Added to Radarr: {movie['title']}")
    return True

# === Main Processing ===
def process_queue():
    print("🔄 Checking Notion for new confirmed media...")
    try:
        entries = query_notion()
        print(f"✅ Pulled {len(entries)} entries from Notion.")
        for entry in entries:
            props = entry["properties"]
            confirmed = props.get("Confirmed", {}).get("checkbox", False)
            added = props.get("Added", {}).get("checkbox", False)
            title_field = props.get("Raw Title", {}).get("title", [])
            notes_field = props.get("Notes", {}).get("multi_select", [])

            if not title_field or not notes_field:
                continue

            title = title_field[0]["text"]["content"]
            type_labels = [item["name"] for item in notes_field]

            if not confirmed or added:
                continue

            if "TV" in type_labels:
                tvdb_id = props.get("TVDB ID", {}).get("number")
                if not tvdb_id:
                    print(f"❌ No TVDB ID found for {title}")
                    continue
                print(f"📺 Processing TV Show: {title} (TVDB ID: {tvdb_id})")
                match = lookup_tv_show(tvdb_id)
                if not match:
                    print(f"❌ No match found in Sonarr for TVDB ID {tvdb_id}")
                    continue
                if add_tv_to_sonarr(match):
                    copy_to_completed_database(title, type_labels, tvdb_id=tvdb_id)
                    archive_notion_page(entry["id"])

            elif "Movie" in type_labels:
                tmdb_id = props.get("TMDB ID", {}).get("number")
                if not tmdb_id:
                    print(f"❌ No TMDB ID found for {title}")
                    continue
                print(f"🎬 Processing Movie: {title} (TMDB ID: {tmdb_id})")
                match = lookup_movie(tmdb_id)
                if not match:
                    print(f"❌ No match found in Radarr for TMDB ID {tmdb_id}")
                    continue
                if add_movie_to_radarr(match):
                    copy_to_completed_database(title, type_labels, tmdb_id=tmdb_id)
                    archive_notion_page(entry["id"])
    except Exception as e:
        print(f"⚠️ Error while processing queue: {e}")

def main():
    print("🟢 Notion → Sonarr/Radarr automation started.")
    print("\n⏱ Polling every 60 seconds...\n")
    while True:
        process_queue()
        time.sleep(60)

if __name__ == "__main__":
    main()
