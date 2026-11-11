"""Streamlit front end: a simulated owner screen for the traffic-light email assistant.

Run with:  streamlit run app.py
"""
import os
import uuid

import pandas as pd
import streamlit as st
from langgraph.types import Command

import venue
from graph import build_graph

st.set_page_config(page_title="Traffic-Light Inbox", page_icon="🚦", layout="wide")

if not (os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_API_TOKEN")):
    st.error("No OpenAI key found. Put OPENAI_API_KEY=... in a .env file next to app.py.")
    st.stop()

venue.init_db()


# cache_resource: build the graph ONCE and keep it across re-runs.
# Otherwise every click would create a new graph and forget the paused emails.
@st.cache_resource
def get_graph():
    return build_graph()


graph = get_graph()

if "threads" not in st.session_state:
    st.session_state.threads = []   # one LangGraph thread id per processed email

COLORS = {"green": "🟢", "yellow": "🟡", "red": "🔴"}
SAMPLES = {
    "(write your own)": "",
    "Hours and parking": "Hi! What time do you open on Sunday, and is there parking nearby?",
    "80 people for $500": "Hey, can you host 80 people this Saturday for $500? It's for my company party.",
    "Patio birthday + cake": "Hello, we'd like the patio for about 20 people next Wednesday for a birthday. "
                             "Can we bring our own cake? What would it cost?",
    "Complaint + refund": "We had dinner at your place last Friday. The food was cold and we waited an hour. "
                          "I want a refund.",
}

# ---------- Sidebar: the owner's settings ----------
with st.sidebar:
    st.header("⚙️ Owner settings")
    green_categories = st.multiselect(
        "Categories the AI may send without asking me",
        ["info", "inquiry", "booking", "complaint", "refund", "other"],
        default=["info"],
        help="Start small. Promote categories to green as you start trusting the AI.",
    )
    st.caption("Prices, dates, and promises always wait for you, whatever you pick here.")

st.title(f"🚦 {venue.VENUE_NAME}: Traffic-Light Inbox")
inbox_tab, venue_tab = st.tabs(["📥 Inbox", "🏠 Venue data"])

# ---------- Inbox ----------
with inbox_tab:
    st.subheader("Simulate an incoming email")
    sample = st.selectbox("Pick a sample", list(SAMPLES))
    email = st.text_area("Customer email", value=SAMPLES[sample], height=100)

    if st.button("📨 Receive email", type="primary", disabled=not email.strip()):
        thread_id = str(uuid.uuid4())
        config = {"configurable": {"thread_id": thread_id}}
        with st.spinner("Understanding → looking up → drafting → checking..."):
            graph.invoke({"email": email, "green_categories": green_categories}, config)
        st.session_state.threads.insert(0, thread_id)

    st.divider()
    if not st.session_state.threads:
        st.info("No emails yet. Pick a sample above and click **Receive email**.")

    for thread_id in st.session_state.threads:
        config = {"configurable": {"thread_id": thread_id}}
        snapshot = graph.get_state(config)
        s = snapshot.values
        waiting = bool(snapshot.next)  # graph is paused at owner_review

        with st.container(border=True):
            header = f"{COLORS[s['color']]} **{s['color'].upper()}**: {s['request']['summary']}"
            st.markdown(header)
            st.caption("Customer: " + s["email"])
            st.markdown("**Why this color:** " + "; ".join(s["reasons"]))

            if waiting:
                edited = st.text_area("AI draft (edit if needed)", s["draft"]["reply"],
                                      height=160, key=f"text_{thread_id}")
                c1, c2, _ = st.columns([1, 1, 4])
                if c1.button("✅ Approve & send", key=f"ok_{thread_id}"):
                    graph.invoke(Command(resume={"action": "approve", "text": edited}), config)
                    st.rerun()
                if c2.button("🗑️ Reject", key=f"no_{thread_id}"):
                    graph.invoke(Command(resume={"action": "reject"}), config)
                    st.rerun()
            else:
                labels = {"sent_automatically": "✉️ Sent automatically",
                          "sent_after_approval": "✉️ Sent after your approval",
                          "rejected": "🗑️ Rejected, not sent"}
                st.markdown(f"**{labels.get(s.get('status'), s.get('status'))}**")
                if s.get("final_reply"):
                    st.text(s["final_reply"])

            with st.expander("🔍 What the AI looked up"):
                st.write("**Understood request:**", s["request"])
                st.write("**Rooms (from database):**")
                st.dataframe(pd.DataFrame(s["rooms"]), hide_index=True)
                st.write("**Policies (from RAG):**")
                for p in s["policies"]:
                    st.markdown(f"- {p}")
                st.write("**Claims in the draft:**",
                         {k: v for k, v in s["draft"].items() if k != "reply"})

# ---------- Venue data (the owner edits numbers here, not in prompts) ----------
with venue_tab:
    st.subheader("Rooms and prices")
    st.caption("The AI reads these live from the database. Change a price and the next reply uses it.")
    edited_rooms = st.data_editor(pd.DataFrame(venue.get_rooms()), num_rows="dynamic", hide_index=True)
    if st.button("💾 Save"):
        venue.save_rooms(edited_rooms.dropna().to_dict("records"))
        st.success("Saved.")
    st.subheader("Policies (searched with RAG)")
    for p in venue.POLICIES:
        st.markdown(f"- {p}")
