import streamlit as st
import requests
import re

# Load secrets
NOTION_TOKEN = st.secrets["NOTION_TOKEN"]
DATABASE_ID = st.secrets["DATABASE_ID"]
TMDB_API_KEY = st.secrets["TMDB_API_KEY"]
DEEPSEEK_API_KEY = st.secrets["DEEPSEEK_API_KEY"]
SONARR_API_KEY = st.secrets["SONARR_API_KEY"]
SONARR_URL = st.secrets["SONARR_URL"]
RADARR_API_KEY = st.secrets["RADARR_API_KEY"]
RADARR_URL = st.secrets["RADARR_URL"]
ROOT_FOLDER_TV = st.secrets["ROOT_FOLDER_TV"]
ROOT_FOLDER_MOVIE = st.secrets["ROOT_FOLDER_MOVIE"]

notion_headers = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json"
}

def fetch_genres(tmdb_id, mode):
    endpoint = "tv" if mode == "tv" else "movie"
    url = f"https://api.themoviedb.org/3/{endpoint}/{tmdb_id}?api_key={TMDB_API_KEY}"
    res = requests.get(url)
    return [g["name"] for g in res.json().get("genres", [])] if res.ok else []

def search_tmdb(query, mode):
    endpoint = "tv" if mode == "tv" else "movie"
    url = f"https://api.themoviedb.org/3/search/{endpoint}?api_key={TMDB_API_KEY}&query={query}"
    res = requests.get(url)
    if not res.ok:
        return []
    results = res.json().get("results", [])
    shows = []
    for r in results[:5]:
        genres = fetch_genres(r["id"], mode)
        shows.append({
            "name": r["name"] if mode == "tv" else r["title"],
            "year": r.get("first_air_date", r.get("release_date", "N/A"))[:4],
            "tmdb_id": r["id"],
            "genres": genres
        })
    return shows

def fallback_deepseek(query, mode):
    prompt = (
        f"The user typed '{query}', which is likely a typo or alternate spelling. "
        f"Return a numbered list of the top 5 real {mode} titles they most likely meant. "
        f"Favor popular or well-known results. Do not include commentary or descriptions."
    )
    res = requests.post(
        "https://api.deepseek.com/chat/completions",
        headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}"},
        json={"model": "deepseek-chat", "messages": [{"role": "user", "content": prompt}]}
    )
    if not res.ok:
        return []
    lines = re.findall(r"\d+\.\s+(.+)", res.json()["choices"][0]["message"]["content"])
    return [s for s in lines[:5] if s]

def get_external_id(tmdb_id, mode):
    endpoint = "tv" if mode == "tv" else "movie"
    url = f"https://api.themoviedb.org/3/{endpoint}/{tmdb_id}/external_ids?api_key={TMDB_API_KEY}"
    res = requests.get(url)
    res.raise_for_status()
    return res.json().get("tvdb_id") if mode == "tv" else tmdb_id

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
    requests.post("https://api.notion.com/v1/pages", headers=notion_headers, json=payload).raise_for_status()

# Streamlit UI
st.set_page_config(page_title="🏴‍☠️ Pirrate ⚓", page_icon="🏴‍☠️")
st.title("🏴‍☠️ Pirrate ⚓")

if "step" not in st.session_state:
    st.session_state.step = "landing"
if "mode" not in st.session_state:
    st.session_state.mode = None
if "suggestions" not in st.session_state:
    st.session_state.suggestions = []
if "selected_show" not in st.session_state:
    st.session_state.selected_show = []

# Step 0
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

# Step 1
elif st.session_state.step == "input":
    with st.form("form_input"):
        query = st.text_input(f"Enter a {'TV show' if st.session_state.mode == 'tv' else 'movie'} title:")
        col1, col2 = st.columns(2)
        submit = col1.form_submit_button("Submit")
        back = col2.form_submit_button("Go Back")
        if submit and query.strip():
            with st.spinner("Searching TMDb..."):
                results = search_tmdb(query, st.session_state.mode)
                if not results:
                    alt_titles = fallback_deepseek(query, st.session_state.mode)
                    st.session_state.suggestions = search_tmdb("|".join(alt_titles), st.session_state.mode)
                else:
                    st.session_state.suggestions = results
                st.session_state.step = "suggestions"
                st.rerun()
        elif back:
            st.session_state.step = "landing"
            st.rerun()

# Step 2
elif st.session_state.step == "suggestions":
    st.subheader("Shows found:" if st.session_state.mode == "tv" else "Movies found:")
    for i, s in enumerate(st.session_state.suggestions, 1):
        genres = f" ({', '.join(s['genres'])})" if s.get("genres") else ""
        st.markdown(f"**{i}.** {s['name']} ({s['year']}){genres}")

    with st.form("form_select"):
        selection = st.text_input("Enter numbers or names (e.g. 1 3 5 or Title Name):")
        col1, col2 = st.columns(2)
        confirm = col1.form_submit_button("Confirm")
        back = col2.form_submit_button("Go Back")
        if confirm:
            picked = []

            nums = set(map(int, re.findall(r"\d+", selection)))
            for i in nums:
                if 1 <= i <= len(st.session_state.suggestions):
                    picked.append(st.session_state.suggestions[i - 1])

            if not picked:
                for s in st.session_state.suggestions:
                    if selection.strip().lower() == s["name"].lower():
                        picked = [s]
                        break

            if picked:
                st.session_state.selected_show = picked
                st.session_state.step = "confirm"
                st.rerun()
            else:
                st.warning("❗ Invalid selection.")
        elif back:
            st.session_state.step = "input"
            st.rerun()

# Step 3
elif st.session_state.step == "confirm":
    for s in st.session_state.selected_show:
        st.success(f"Selected: {s['name']} ({s['year']})")

    with st.form("form_confirm"):
        col1, col2 = st.columns(2)
        submit = col1.form_submit_button("Confirm Download")
        back = col2.form_submit_button("Go Back")
        if submit:
            for s in st.session_state.selected_show:
                try:
                    eid = get_external_id(s["tmdb_id"], st.session_state.mode)
                    send_to_notion(s["name"], eid, st.session_state.mode)
                    st.success(f"✅ {s['name']} sent to Notion.")
                except Exception as e:
                    st.error(f"❌ Failed to submit {s['name']}: {e}")
            st.session_state.step = "done"
            st.rerun()
        elif back:
            st.session_state.step = "suggestions"
            st.rerun()

# Step 4
elif st.session_state.step == "done":
    if st.button("➕ Add Another Media"):
        st.session_state.step = "landing"
        st.session_state.mode = None
        st.session_state.suggestions = []
        st.session_state.selected_show = []
        st.rerun()
    st.success("✅ Your media has been successfully submitted!")
