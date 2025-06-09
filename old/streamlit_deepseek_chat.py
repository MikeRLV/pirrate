import streamlit as st
import requests
import os
from dotenv import load_dotenv

# Load .env variables
load_dotenv()
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

# Headers
notion_headers = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json"
}
deepseek_headers = {
    "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
    "Content-Type": "application/json"
}

# DeepSeek
def get_suggestions_from_deepseek(query):
    prompt = f"""
A user typed: "{query}"
Return a list of up to 5 exact or closely matching TV show titles, ideally with year and country.
Format:
- Title (Year, Country)
"""
    data = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": "You are a TV title lookup assistant."},
            {"role": "user", "content": prompt}
        ]
    }
    try:
        response = requests.post("https://api.deepseek.com/chat/completions", headers=deepseek_headers, json=data)
        response.raise_for_status()
        text = response.json()["choices"][0]["message"]["content"]
        return [line.strip("•- ").strip() for line in text.split("\n") if line.strip()][:5]
    except Exception as e:
        st.error(f"DeepSeek API error: {e}")
        return []

# Notion
def send_to_notion(title, notes):
    payload = {
        "parent": {"database_id": DATABASE_ID},
        "properties": {
            "Raw Title": {"title": [{"text": {"content": title}}]},
            "Notes": {"rich_text": [{"text": {"content": notes}}]},
            "Confirmed": {"checkbox": True},
            "Added to Sonarr": {"checkbox": False},
            "System Response": {"rich_text": [{"text": {"content": "⏳ Waiting to be processed"}}]}
        }
    }
    response = requests.post("https://api.notion.com/v1/pages", headers=notion_headers, json=payload)
    response.raise_for_status()

# UI Setup
st.set_page_config(page_title="TV Show Request (DeepSeek)", page_icon="🎬")
st.title("🎬 TV Show Request Assistant")

# Session state
if "query" not in st.session_state:
    st.session_state.query = ""
if "suggestions" not in st.session_state:
    st.session_state.suggestions = []
if "submitted" not in st.session_state:
    st.session_state.submitted = False
if "selected" not in st.session_state:
    st.session_state.selected = None

# ✅ After successful submission
if st.session_state.submitted:
    st.success("✅ Show submitted successfully!")
    if st.button("Submit another request"):
        # Full manual reset — no rerun
        st.session_state.query = ""
        st.session_state.suggestions = []
        st.session_state.selected = None
        st.session_state.submitted = False
    st.stop()

# Search input
query_input = st.text_input("Enter a TV show title:", value=st.session_state.query)

if query_input and query_input != st.session_state.query:
    with st.spinner("Asking DeepSeek..."):
        st.session_state.suggestions = get_suggestions_from_deepseek(query_input)
        st.session_state.query = query_input

# Suggestion picker
if st.session_state.suggestions:
    st.subheader("Did you mean:")
    st.session_state.selected = st.radio("Choose one:", st.session_state.suggestions, key="radio_choice")

# Notes and submission
if st.session_state.selected:
    st.success(f"Selected: {st.session_state.selected}")
    notes = st.text_area("Optional notes:", key="notes_field")

    if st.button("✅ Submit to Notion"):
        try:
            send_to_notion(st.session_state.selected, notes)
            st.session_state.submitted = True
        except Exception as e:
            st.error(f"❌ Failed to submit: {e}")
