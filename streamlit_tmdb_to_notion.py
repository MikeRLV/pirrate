import streamlit as st
import requests
import json

# Load secrets
NOTION_TOKEN = st.secrets["NOTION_TOKEN"]
DATABASE_ID = st.secrets["DATABASE_ID"]
TMDB_API_KEY = st.secrets["TMDB_API_KEY"]
SONARR_API_KEY = st.secrets["SONARR_API_KEY"]
SONARR_URL = st.secrets["SONARR_URL"]
DEEPSEEK_API_KEY = st.secrets["DEEPSEEK_API_KEY"]
RADARR_API_KEY = st.secrets["RADARR_API_KEY"]
RADARR_URL = st.secrets["RADARR_URL"]
ROOT_FOLDER_TV = st.secrets["ROOT_FOLDER_TV"]
ROOT_FOLDER_MOVIE = st.secrets["ROOT_FOLDER_MOVIE"]

notion_headers = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json"
}

def get_tmdb_details(tmdb_id, mode):
    url = f"https://api.themoviedb.org/3/{mode}/{tmdb_id}?api_key={TMDB_API_KEY}"
    response = requests.get(url)
    if response.status_code != 200:
        return []
    return [g["name"] for g in response.json().get("genres", [])]

def search_tmdb(query, mode):
    endpoint = "tv" if mode == "tv" else "movie"
    url = f"https://api.themoviedb.org/3/search/{endpoint}?api_key={TMDB_API_KEY}&query={query}"
    response = requests.get(url)
    if response.status_code != 200 or not response.json().get("results"):
        return search_deepseek(query, mode)

    shows = []
    for r in response.json().get("results", [])[:5]:
        genres = get_tmdb_details(r["id"], endpoint)
        shows.append({
            "name": r["name"] if mode == "tv" else r["title"],
            "year": (r.get("first_air_date") or r.get("release_date") or "N/A")[:4],
            "tmdb_id": r["id"],
            "genres": genres
        })
    return shows

def search_deepseek(query, mode):
    prompt = f"List 5 {mode} titles similar to '{query}' with TMDB IDs and genres. Format as JSON list with 'name', 'tmdb_id', 'year', and 'genres'."
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}]
    }
    try:
        response = requests.post("https://api.deepseek.com/v1/chat/completions", headers=headers, json=payload)
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        return json.loads(content)
    except Exception as e:
        st.error(f"❌ DeepSeek failed: {e}")
        return []

def get_external_id(tmdb_id, mode):
    url = f"https://api.themoviedb.org/3/{mode}/{tmdb_id}/external_ids?api_key={TMDB_API_KEY}"
    response = requests.get(url)
    response.raise_for_status()
    return response.json().get("tvdb_id") if mode == "tv" else tmdb_id

def send_to_notion(title, external_id, mode):
    id_field = "TVDB ID" if mode == "tv" else "TMDB ID"
    payload = {
        "parent": {"database_id": DATABASE_ID},
        "properties": {
            "Raw Title": {"title": [{"text": {"content": title}}]},
            id_field: {"number": external_id if external_id else 0},
            "Notes": {"multi_select": [{"name": "TV"}] if mode == "tv" else [{"name": "Movie"}]},
            "Confirmed": {"checkbox": True},
            "Added": {"checkbox": False},
            "System Response": {"rich_text": [{"text": {"content": "⏳ Waiting to be processed"}}]}
        }
    }
    response = requests.post("https://api.notion.com/v1/pages", headers=notion_headers, json=payload)
    response.raise_for_status()

# ─────────────────────────── Streamlit UI ─────────────────────────── #
st.set_page_config(page_title="🏴‍☠️ Pirrate ⚓", page_icon="🏴‍☠️")
st.title("🏴‍☠️ Pirrate ⚓")

if "step" not in st.session_state:
    st.session_state.step = "landing"
if "mode" not in st.session_state:
    st.session_state.mode = None
if "suggestions" not in st.session_state:
    st.session_state.suggestions = []
if "selected_show" not in st.session_state:
    st.session_state.selected_show = {}

# Step 0: Landing
if st.session_state.step == "landing":
    st.subheader("What would you like to search for?")
    col1, col2 = st.columns(2)
    if col1.button("📺 TV Shows"):
        st.session_state.mode = "tv"
        st.session_state.step = "input"
        st.rerun()
    if col2.button("🎬 Movies"):
        st.session_state.mode = "movie"
        st.session_state.step = "input"
        st.rerun()

# Step 1: Search
elif st.session_state.step == "input":
    with st.form(key="form_input"):
        query = st.text_input(f"Enter a { 'TV show' if st.session_state.mode == 'tv' else 'movie' } title:")
        col1, col2 = st.columns(2)
        submit = col1.form_submit_button("Submit")
        back = col2.form_submit_button("Go Back")
        if submit and query.strip():
            with st.spinner("🔍 Searching..."):
                st.session_state.suggestions = search_tmdb(query, st.session_state.mode)
                st.session_state.step = "suggestions"
                st.rerun()
        elif back:
            st.session_state.step = "landing"
            st.rerun()

# Step 2: Suggestions
elif st.session_state.step == "suggestions":
    st.subheader("Shows found:" if st.session_state.mode == "tv" else "Movies found:")
    for i, s in enumerate(st.session_state.suggestions, 1):
        genre_text = f" ({', '.join(s['genres'])})" if s.get("genres") else ""
        st.markdown(f"**{i}.** {s['name']} ({s['year']}){genre_text}")
    with st.form(key="form_select"):
        selection = st.text_input("Type the number or full title of your choice:")
        col1, col2 = st.columns(2)
        confirm = col1.form_submit_button("Confirm")
        back = col2.form_submit_button("Go Back")

        picked = None
        if confirm:
            tokens = selection.replace(",", " ").split()
            for token in tokens:
                if token.isdigit():
                    index = int(token) - 1
                    if 0 <= index < len(st.session_state.suggestions):
                        picked = st.session_state.suggestions[index]
                        break
                else:
                    for show in st.session_state.suggestions:
                        if token.lower() == show["name"].lower():
                            picked = show
                            break
            if picked:
                st.session_state.selected_show = picked
                st.session_state.step = "confirm"
                st.rerun()
            else:
                st.warning("❗ Invalid selection.")
        elif back:
            st.session_state.step = "input"
            st.session_state.suggestions = []
            st.rerun()

# Step 3: Confirm
elif st.session_state.step == "confirm":
    show = st.session_state.selected_show
    st.success(f"Selected: {show['name']} ({show['year']})")
    with st.form(key="form_confirm"):
        col1, col2 = st.columns(2)
        submit = col1.form_submit_button("Confirm Download")
        back = col2.form_submit_button("Go Back")
        if submit:
            try:
                external_id = get_external_id(show["tmdb_id"], st.session_state.mode)
                send_to_notion(show["name"], external_id, st.session_state.mode)
                st.success("✅ Show submitted successfully and ready for Sonarr/Radarr.")
                st.session_state.step = "done"
                st.rerun()
            except Exception as e:
                st.error(f"❌ Failed to submit: {e}")
        elif back:
            st.session_state.step = "suggestions"
            st.rerun()

# Step 4: Done
elif st.session_state.step == "done":
    if st.button("➕ Add Another Media"):
        st.session_state.step = "landing"
        st.session_state.mode = None
        st.session_state.suggestions = []
        st.session_state.selected_show = {}
        st.rerun()
    st.success("✅ Your media has been successfully submitted!")
