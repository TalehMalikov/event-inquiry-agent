import os
import re
import uuid
from dotenv import load_dotenv

load_dotenv()
# Local fix: Anaconda on this machine points SSL_CERT_FILE at a missing file
if os.getenv("SSL_CERT_FILE") and not os.path.exists(os.environ["SSL_CERT_FILE"]):
	del os.environ["SSL_CERT_FILE"]

import streamlit as st
# Set the title using StreamLit
st.title(' 🚦 Event Venue Email Assistant ')
st.caption('Every email gets a draft. The traffic light decides: send now, or wait for the owner?')
input_text = st.text_area('Paste a customer email:')


from langchain_core.prompts import PromptTemplate
# setting up the prompt templates
classify_template = PromptTemplate(
	input_variables = ['email'],
	template='''Classify this customer email to an event venue. Answer with ONE word only:
	info (hours, parking, menu), inquiry (asking about hosting an event), booking, complaint, refund, or other.
	Email: {email}'''
)

draft_template = PromptTemplate(
	input_variables = ['email', 'venue_facts'],
	template='''You reply to emails for The Copper Kettle, an event venue. Be warm and brief.
	Use ONLY these facts, never invent prices or capacities: {venue_facts}
	If the request doesn't fit (too many guests, budget too low), say so kindly and offer options that fit.
	If a fact is missing, say you'll check with the team. Never confirm a booking yourself.
	Customer email: {email}'''
)


from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser
# Importing the large language model OpenAI via langchain
model = ChatOpenAI(
	model="gpt-4.1-mini",
	temperature=0.3,
	api_key=os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_API_TOKEN"),
)

# prompt -> model -> parser, same as chatbot_example.py
chainC = classify_template | model | StrOutputParser()
chainD = draft_template | model | StrOutputParser()


# The venue's facts (in a real app: prices in a database, policies in a RAG index)
VENUE_FACTS = [
	"Main Hall: up to 60 guests. Minimum spend $500 on weekdays, $800 on weekends.",
	"Garden Patio: up to 30 guests. Minimum spend $250 on weekdays, $400 on weekends.",
	"Hours: open Tuesday to Sunday, 11am to 11pm. Closed Mondays.",
	"Parking: free lot behind the building with 25 spaces, plus street parking on Elm St.",
	"Deposits: a 25% deposit holds the date. Full refund if cancelled 14+ days before.",
	"Food: all food from our kitchen. Outside cakes allowed for a $2/person fee.",
	"Menu: wood-fired pizza, salads, local craft beer. Vegetarian and gluten-free options.",
]
MAX_GUESTS = 60

def venue_lookup(query, top_k=3):
	"""Find the venue facts that share the most words with the email (a simple stand-in for RAG)."""
	words = set(re.findall(r"[a-z]+", query.lower()))
	scored = sorted(VENUE_FACTS, key=lambda fact: -len(words & set(re.findall(r"[a-z]+", fact.lower()))))
	# Always include the room facts, so prices and capacities are never guessed
	return "\n".join(dict.fromkeys(VENUE_FACTS[:2] + scored[:top_k]))


def traffic_light(category, draft):
	"""Plain code rules, not the LLM's opinion. When unsure: wait for the owner."""
	reasons = []
	if category in ("complaint", "refund"):
		return "red", [f"Sensitive topic: {category}"]
	# Too many guests is only a problem if the draft offers it, not if it politely declines it
	declining = re.search(r"\b(can['’]t|cannot|can not|unable|unfortunately|only up to|up to \d+)\b", draft, re.I)
	guests = [int(n) for n in re.findall(r"(\d+)\s*(?:guests|people)", draft)]
	if any(n > MAX_GUESTS for n in guests) and not declining:
		return "red", [f"Draft offers more than {MAX_GUESTS} guests"]
	if "$" in draft:
		reasons.append("Reply includes a price")
	if re.search(r"\b(confirm|booked|reserved|see you on)\b", draft, re.I):
		reasons.append("Reply may commit to a date or booking")
	if category != "info":
		reasons.append(f"Category '{category}' is not on the green list")
	return ("yellow", reasons) if reasons else ("green", ["Informational, no price or promise"])


# ---------- LangGraph: connect the steps into a graph ----------
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt, Command
from langgraph.checkpoint.memory import InMemorySaver

class State(TypedDict, total=False):
	email: str
	category: str
	venue_facts: str
	draft: str
	color: str
	reasons: list
	final_reply: str
	status: str

def classify_node(state):
	return {'category': chainC.invoke({'email': state['email']}).strip().lower().strip('.')}

def lookup_node(state):
	return {'venue_facts': venue_lookup(state['email'])}

def draft_node(state):
	return {'draft': chainD.invoke({'email': state['email'], 'venue_facts': state['venue_facts']})}

def light_node(state):
	color, reasons = traffic_light(state['category'], state['draft'])
	return {'color': color, 'reasons': reasons}

def owner_node(state):
	# Pause here until the owner clicks a button. The checkpointer saves everything meanwhile.
	decision = interrupt(state['draft'])
	if decision['action'] == 'reject':
		return {'status': 'Rejected, not sent'}
	return {'final_reply': decision['text'], 'status': 'Sent after owner approval'}

def send_node(state):
	if state['color'] == 'green':
		return {'final_reply': state['draft'], 'status': 'Sent automatically'}
	return {}

@st.cache_resource  # build the graph once, so paused emails survive Streamlit re-runs
def build_graph():
	g = StateGraph(State)
	g.add_node('classify', classify_node)
	g.add_node('lookup', lookup_node)
	g.add_node('draft', draft_node)
	g.add_node('traffic_light', light_node)
	g.add_node('owner_review', owner_node)
	g.add_node('send', send_node)
	g.add_edge(START, 'classify')
	g.add_edge('classify', 'lookup')
	g.add_edge('lookup', 'draft')
	g.add_edge('draft', 'traffic_light')
	g.add_conditional_edges('traffic_light', lambda s: 'send' if s['color'] == 'green' else 'owner_review')
	g.add_conditional_edges('owner_review', lambda s: END if s['status'].startswith('Rejected') else 'send')
	g.add_edge('send', END)
	return g.compile(checkpointer=InMemorySaver())

graph = build_graph()


# Display the output if the user gives an input
if st.button('Process email', disabled=not input_text):
	st.session_state.thread_id = str(uuid.uuid4())
	with st.spinner('Thinking...'):
		graph.invoke({'email': input_text}, {'configurable': {'thread_id': st.session_state.thread_id}})

if 'thread_id' in st.session_state:
	config = {'configurable': {'thread_id': st.session_state.thread_id}}
	snapshot = graph.get_state(config)
	result = snapshot.values
	icon = {'green': '🟢', 'yellow': '🟡', 'red': '🔴'}[result['color']]

	st.subheader(f"{icon} {result['color'].upper()} ({result['category']})")
	st.write('Why: ' + '; '.join(result['reasons']))

	if snapshot.next:  # paused at owner_review
		edited = st.text_area('Draft (edit if needed):', result['draft'], height=200)
		col1, col2 = st.columns(2)
		if col1.button('✅ Approve & send'):
			graph.invoke(Command(resume={'action': 'approve', 'text': edited}), config)
			st.rerun()
		if col2.button('🗑️ Reject'):
			graph.invoke(Command(resume={'action': 'reject'}), config)
			st.rerun()
	else:
		st.success(result['status'])
		if result.get('final_reply'):
			st.write(result['final_reply'])

	with st.expander('Venue facts the AI used: '):
		st.info(result['venue_facts'])
