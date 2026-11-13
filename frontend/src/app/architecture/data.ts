// Everything the /architecture page draws. Positions are in diagram pixels; children are relative to their group.

export type Kind = "person" | "vercel" | "ext" | "data" | "ai" | "off" | "code";

export type Info = {
  title: string;
  tech: string;
  icon: string;
  kind: Kind;
  what: string;
  facts?: string[];
  code?: string[];
};

export type Box = { id: string; label: string; x: number; y: number; w: number; h: number; tone: string };
export type Item = Info & { id: string; parent?: string; x: number; y: number };
export type Link = { id: string; from: string; to: string; label?: string; off?: boolean };
export type Step = { text: string; nodes: string[]; links: string[] };
export type Flow = { id: string; title: string; summary: string; steps: Step[] };

// ---------------------------------------------------------------- System map

export const SYSTEM_BOXES: Box[] = [
  { id: "g-people", label: "People", x: 0, y: 0, w: 260, h: 390, tone: "slate" },
  { id: "g-dev", label: "Code & deploy", x: 0, y: 440, w: 260, h: 280, tone: "slate" },
  { id: "g-net", label: "Internet", x: 320, y: 0, w: 260, h: 280, tone: "slate" },
  { id: "g-vercel", label: "Vercel · region iad1 (Washington, DC)", x: 640, y: 0, w: 560, h: 720, tone: "zinc" },
  { id: "g-upstash", label: "Upstash (Vercel Marketplace)", x: 640, y: 760, w: 260, h: 170, tone: "emerald" },
  { id: "g-clerk", label: "Clerk (Vercel Marketplace)", x: 1260, y: 0, w: 260, h: 170, tone: "violet" },
  { id: "g-openai", label: "OpenAI", x: 1260, y: 210, w: 260, h: 280, tone: "teal" },
  { id: "g-neon", label: "Neon Postgres · iad1 (Vercel Marketplace)", x: 1260, y: 530, w: 260, h: 400, tone: "sky" },
  { id: "g-google", label: "Google", x: 1580, y: 0, w: 260, h: 390, tone: "amber" },
  { id: "g-ms", label: "Microsoft", x: 1580, y: 430, w: 260, h: 280, tone: "blue" },
  { id: "g-push", label: "Phone push services", x: 1580, y: 750, w: 260, h: 180, tone: "rose" },
];

export const SYSTEM_ITEMS: Item[] = [
  {
    id: "customer", parent: "g-people", x: 20, y: 50, icon: "✉️", kind: "person",
    title: "Customer", tech: "Any email app",
    what: "Someone asking the venue a question or for a booking. They only ever see a normal email reply: never colors, labels or reasons.",
  },
  {
    id: "phone", parent: "g-people", x: 20, y: 160, icon: "📱", kind: "person",
    title: "Owner's phone", tech: "Installed app (PWA) + service worker",
    what: "The web app installed on the home screen (Android and iPhone). Its service worker (public/sw.js) shows the short colored notification and handles the Send / Decline buttons, even when the app is closed.",
    facts: ["Install: manifest.ts + the Install button", "Tap = opens the email in the app", "Send / Decline work without opening the app (one-time 48 h keys)"],
    code: ["frontend/public/sw.js", "frontend/src/app/manifest.ts", "frontend/src/components/InstallApp.tsx"],
  },
  {
    id: "laptop", parent: "g-people", x: 20, y: 270, icon: "💻", kind: "person",
    title: "Owner's browser", tech: "events.tmalikov.com",
    what: "Inbox, one-screen approve page, Company data (rooms, prices, policies), Settings (connect inbox, notifications, auto-send rules).",
  },
  {
    id: "github", parent: "g-dev", x: 20, y: 50, icon: "🐙", kind: "code",
    title: "GitHub", tech: "event-inquiry-agent · branch product",
    what: "The code. Branch main = the homework (Streamlit), branch product = this app. Deploys go from the Vercel CLI (vercel deploy --prod) in backend/ and frontend/.",
  },
  {
    id: "docker", parent: "g-dev", x: 20, y: 160, icon: "🐳", kind: "code",
    title: "Docker Compose", tech: "Local copy: db + backend + frontend",
    what: "Runs the whole system on a laptop (Postgres with pgvector, FastAPI, Next.js) for development and the automated tests.",
    code: ["docker-compose.yml", "backend/tests/*.py"],
  },
  {
    id: "dns", parent: "g-net", x: 20, y: 50, icon: "🌐", kind: "ext",
    title: "GoDaddy DNS", tech: "CNAME events → Vercel",
    what: "tmalikov.com is registered at GoDaddy. One CNAME record points events.tmalikov.com at Vercel, which issues the HTTPS certificate.",
  },
  {
    id: "edge", parent: "g-net", x: 20, y: 160, icon: "🛡️", kind: "vercel",
    title: "Vercel edge network", tech: "HTTPS, CDN, routing",
    what: "Terminates HTTPS, serves cached static files (icons, scripts) close to the user and routes everything else to the Next.js app.",
  },
  {
    id: "proxy", parent: "g-vercel", x: 20, y: 50, icon: "🚦", kind: "vercel",
    title: "proxy.ts", tech: "Clerk middleware (Next.js 16)",
    what: "Runs before every page: not signed in → sign-in page; signed in but no company yet → choose a company. /api, sign-in and this page are public (the backend checks /api itself).",
    code: ["frontend/src/proxy.ts"],
  },
  {
    id: "next", parent: "g-vercel", x: 20, y: 160, icon: "▲", kind: "vercel",
    title: "Next.js app", tech: "events-frontend · React 19 · Tailwind",
    what: "All screens. The browser calls /api/... on the same domain and Next.js forwards it to the backend, so there is no CORS and the backend URL stays hidden.",
    facts: ["Pages: Inbox, /m/[id], Company data, Settings, Architecture", "Checks for new mail every 15 s while open"],
    code: ["frontend/src/app/", "frontend/next.config.ts (rewrite /api → backend)"],
  },
  {
    id: "cron", parent: "g-vercel", x: 20, y: 600, icon: "⏰", kind: "vercel",
    title: "Vercel Cron", tech: "Daily 09:00 UTC (backup)",
    what: "A daily safety net that calls the mail check, in case the 15-minute schedule ever misses.",
    code: ["backend/vercel.json"],
  },
  {
    id: "api", parent: "g-vercel", x: 300, y: 50, icon: "⚡", kind: "vercel",
    title: "FastAPI backend", tech: "events-backend · Python 3.12 · serverless",
    what: "The API. Checks the Clerk login token on every request and takes the company ONLY from that token, so one company can never read another's data. Admins edit company data; members work the inbox.",
    facts: ["Daily AI-draft limit per company (50)", "Starts lazily: the agent and DB pools are created on the first request"],
    code: ["backend/app/main.py", "backend/app/auth.py"],
  },
  {
    id: "mail", parent: "g-vercel", x: 300, y: 160, icon: "📬", kind: "vercel",
    title: "Mail connectors", tech: "gmail.py · outlook.py · providers.py",
    what: "One interface, two providers. Reads new mail since the saved position, skips newsletters / robots / no-reply, puts drafts and colored labels (Gmail) or categories (Outlook) in the owner's mailbox, and sends replies in the same thread.",
    facts: ["Never deletes the owner's mail", "Refresh tokens encrypted (Fernet) in the database", "Detects when the owner pressed Send in Gmail/Outlook"],
    code: ["backend/app/gmail.py", "backend/app/outlook.py", "backend/app/mail_api.py"],
  },
  {
    id: "agent", parent: "g-vercel", x: 300, y: 270, icon: "🧠", kind: "ai",
    title: "LangGraph agent", tech: "understand → look_up → draft → traffic light",
    what: "Every email gets a draft. The traffic light (plain code rules, not AI) only decides: send now (green) or wait for the owner (yellow / red). Waiting runs pause with interrupt() and resume when the owner decides. See the 'AI agent' tab.",
    code: ["backend/app/agent.py"],
  },
  {
    id: "rag", parent: "g-vercel", x: 300, y: 380, icon: "📚", kind: "ai",
    title: "RAG", tech: "Policy search per company",
    what: "Finds the company's own policies (hours, parking, deposits…) closest in meaning to the email, so the draft uses real facts. Always filtered by company.",
    code: ["backend/app/rag.py"],
  },
  {
    id: "outbox", parent: "g-vercel", x: 300, y: 490, icon: "📤", kind: "vercel",
    title: "Outbox", tech: "Drafts, colors, sending",
    what: "Everything the agent does in the owner's mailbox: yellow/red → draft in the thread + colored label + phone ping. Approved → send once, remove the draft, label turns green. Declined → draft and color removed.",
    code: ["backend/app/outbox.py"],
  },
  {
    id: "push", parent: "g-vercel", x: 300, y: 600, icon: "🔔", kind: "vercel",
    title: "Web Push sender", tech: "pywebpush · VAPID keys",
    what: "Sends the short notification ('🟡 Approve reply to Mike') to every device of the company that turned notifications on. Send / Decline carry signed one-time keys.",
    code: ["backend/app/push.py"],
  },
  {
    id: "qstash", parent: "g-upstash", x: 20, y: 50, icon: "⏱️", kind: "ext",
    title: "QStash schedule", tech: "Every 15 min → /api/cron/gmail",
    what: "Calls the backend's mail check every 15 minutes, with a secret, for all companies. This replaces instant Google push, which would need a Google billing account.",
  },
  {
    id: "clerk", parent: "g-clerk", x: 20, y: 50, icon: "🔐", kind: "ext",
    title: "Clerk", tech: "Login + organizations = companies",
    what: "Sign up / sign in with Google, Microsoft or email + password. Each Clerk organization is one company; members have admin or member roles. The backend verifies Clerk's signed tokens (RS256, public keys).",
  },
  {
    id: "llm", parent: "g-openai", x: 20, y: 50, icon: "💬", kind: "ai",
    title: "Chat model", tech: "gpt-4.1-mini",
    what: "Two calls per email: 'understand' (category, guests, date, budget, as structured data) and 'draft' (the reply, plus what it quoted and promised, so the rules can check it).",
  },
  {
    id: "embed", parent: "g-openai", x: 20, y: 160, icon: "🔢", kind: "ai",
    title: "Embeddings", tech: "text-embedding-3-small (1536)",
    what: "Turns policies and each email into vectors so the RAG search can match by meaning, not by exact words.",
  },
  {
    id: "tables", parent: "g-neon", x: 20, y: 50, icon: "🗄️", kind: "data",
    title: "Business tables", tech: "companies · rooms · messages · …",
    what: "Companies, rooms and prices, policies, connected mailboxes, every email and what happened to it, phone subscriptions. Every row belongs to one company. See the 'Database' tab.",
    code: ["backend/app/db.py"],
  },
  {
    id: "vector", parent: "g-neon", x: 20, y: 160, icon: "🧭", kind: "data",
    title: "pgvector", tech: "Vector search inside Postgres",
    what: "Policy embeddings live in the same database, so search, company filtering and data stay in one place (no separate vector database).",
  },
  {
    id: "checkpoints", parent: "g-neon", x: 20, y: 270, icon: "⏸️", kind: "data",
    title: "LangGraph checkpoints", tech: "PostgresSaver",
    what: "The saved state of each paused agent run. When the owner taps Send hours later, the run continues exactly where it stopped, on whatever server handles that request.",
  },
  {
    id: "goauth", parent: "g-google", x: 20, y: 50, icon: "🔑", kind: "ext",
    title: "Google OAuth", tech: "Google Cloud project · scope gmail.modify",
    what: "The owner clicks Connect Gmail and approves read, draft, label and send. Testing mode for now (tokens expire weekly → Reconnect); Google app verification before real customers.",
  },
  {
    id: "gmail", parent: "g-google", x: 20, y: 160, icon: "📧", kind: "ext",
    title: "Gmail API", tech: "REST (history, messages, drafts, labels)",
    what: "Where Gmail companies' mail lives. Colored labels: AI · Sent (green), AI · Needs approval (yellow), AI · Needs you (red).",
  },
  {
    id: "pubsub", parent: "g-google", x: 20, y: 270, icon: "📡", kind: "off",
    title: "Pub/Sub push (off)", tech: "Built, switched off",
    what: "Instant 'new mail' pings from Gmail. The code is ready, but it needs a Google billing account, so the 15-minute schedule is used instead. Turned on by setting GMAIL_PUBSUB_TOPIC.",
  },
  {
    id: "entra", parent: "g-ms", x: 20, y: 50, icon: "🔑", kind: "ext",
    title: "Microsoft sign-in", tech: "Entra app · personal + work accounts",
    what: "The owner clicks Connect Outlook and approves Mail.ReadWrite, Mail.Send and categories. Works for outlook.com and for Microsoft 365 if the admin allows it.",
  },
  {
    id: "graph", parent: "g-ms", x: 20, y: 160, icon: "📨", kind: "ext",
    title: "Microsoft Graph", tech: "Outlook mail API",
    what: "Where Outlook companies' mail lives. Reply drafts via createReply, colored categories (green / yellow / red), immutable ids so nothing gets lost when mail moves folders.",
  },
  {
    id: "fcm", parent: "g-push", x: 20, y: 50, icon: "📲", kind: "ext",
    title: "FCM / Apple Push", tech: "Browser push services",
    what: "Google's (Android, Chrome) and Apple's (iPhone) push services deliver our signed notification to the phone, even when the app is closed.",
  },
];

export const SYSTEM_LINKS: Link[] = [
  { id: "cust-gmail", from: "customer", to: "gmail", label: "emails the venue" },
  { id: "cust-graph", from: "customer", to: "graph", label: "or Outlook" },
  { id: "dns-edge", from: "dns", to: "edge", label: "CNAME" },
  { id: "laptop-edge", from: "laptop", to: "edge", label: "HTTPS" },
  { id: "phone-edge", from: "phone", to: "edge", label: "HTTPS" },
  { id: "edge-proxy", from: "edge", to: "proxy", label: "page requests" },
  { id: "proxy-clerk", from: "proxy", to: "clerk", label: "signed in?" },
  { id: "proxy-next", from: "proxy", to: "next" },
  { id: "next-clerk", from: "next", to: "clerk", label: "sign-in UI" },
  { id: "next-api", from: "next", to: "api", label: "/api/* (same origin)" },
  { id: "api-clerk", from: "api", to: "clerk", label: "verify token" },
  { id: "api-tables", from: "api", to: "tables", label: "SQL, per company" },
  { id: "qstash-api", from: "qstash", to: "api", label: "every 15 min" },
  { id: "cron-api", from: "cron", to: "api", label: "daily" },
  { id: "api-mail", from: "api", to: "mail", label: "check inbox" },
  { id: "mail-gmail", from: "mail", to: "gmail", label: "read · draft · label · send" },
  { id: "mail-graph", from: "mail", to: "graph", label: "read · draft · category · send" },
  { id: "mail-goauth", from: "mail", to: "goauth", label: "tokens" },
  { id: "mail-entra", from: "mail", to: "entra", label: "tokens" },
  { id: "gmail-pubsub", from: "gmail", to: "pubsub", label: "instant (off)", off: true },
  { id: "api-agent", from: "api", to: "agent", label: "run per email" },
  { id: "agent-llm", from: "agent", to: "llm", label: "understand + draft" },
  { id: "agent-rag", from: "agent", to: "rag", label: "look_up" },
  { id: "rag-embed", from: "rag", to: "embed" },
  { id: "rag-vector", from: "rag", to: "vector", label: "similar policies" },
  { id: "agent-checkpoints", from: "agent", to: "checkpoints", label: "pause / resume" },
  { id: "agent-outbox", from: "agent", to: "outbox", label: "stage / send" },
  { id: "outbox-mail", from: "outbox", to: "mail" },
  { id: "outbox-push", from: "outbox", to: "push", label: "ping owner" },
  { id: "push-fcm", from: "push", to: "fcm", label: "Web Push (VAPID)" },
  { id: "fcm-phone", from: "fcm", to: "phone", label: "notification" },
  { id: "github-next", from: "github", to: "next", label: "vercel deploy" },
  { id: "github-api", from: "github", to: "api" },
];

export const FLOWS: Flow[] = [
  {
    id: "green",
    title: "🟢 New email, answered automatically",
    summary: "A simple question (opening hours) is answered within minutes, no owner needed.",
    steps: [
      { text: "A customer emails the venue's Gmail (or Outlook): \"When are you open?\"", nodes: ["customer", "gmail", "graph"], links: ["cust-gmail", "cust-graph"] },
      { text: "Every 15 minutes Upstash QStash calls the backend's mail check (the open app also checks every 15 s; Vercel Cron daily as backup).", nodes: ["qstash", "cron", "api"], links: ["qstash-api", "cron-api"] },
      { text: "The mail connector asks Gmail/Outlook for mail since its saved position and skips newsletters, robots and no-reply senders.", nodes: ["api", "mail", "gmail", "graph"], links: ["api-mail", "mail-gmail", "mail-graph"] },
      { text: "The email is saved once in Neon (a unique key stops duplicates) and a LangGraph run starts for it.", nodes: ["api", "tables", "agent"], links: ["api-tables", "api-agent"] },
      { text: "understand: the chat model reads the email and returns structured data: category 'info', no guests, no date.", nodes: ["agent", "llm"], links: ["agent-llm"] },
      { text: "look_up: rooms and prices come from the company's tables; policies come from a pgvector search on the email's meaning.", nodes: ["agent", "rag", "embed", "vector", "tables"], links: ["agent-rag", "rag-embed", "rag-vector"] },
      { text: "draft: the chat model writes the reply using ONLY those facts, signed 'The Copper Oven team'.", nodes: ["agent", "llm"], links: ["agent-llm"] },
      { text: "traffic light: plain code rules. No price, no date, no promise, and 'info' is on the auto-send list → green.", nodes: ["agent"], links: [] },
      { text: "send: the reply goes out from the venue's own mailbox, in the same thread, and the email gets the green 'AI · Sent' label.", nodes: ["agent", "outbox", "mail", "gmail", "graph", "customer"], links: ["agent-outbox", "outbox-mail", "mail-gmail", "mail-graph"] },
    ],
  },
  {
    id: "yellow",
    title: "🟡 Needs approval: owner taps Send on the phone",
    summary: "A price quote waits for the owner, who approves it from the notification in one tap.",
    steps: [
      { text: "\"Can we book for 40 on Saturday?\" arrives and goes through understand → look_up → draft like any email.", nodes: ["customer", "gmail", "mail", "api", "agent", "llm", "rag"], links: ["cust-gmail", "api-mail", "mail-gmail", "api-agent", "agent-llm", "agent-rag"] },
      { text: "traffic light: the reply includes a price → yellow. (A wrong fact, like more guests than the biggest room fits, would be red.)", nodes: ["agent"], links: [] },
      { text: "stage: the draft is placed in the customer's thread in Gmail/Outlook with the yellow 'AI · Needs approval' color, so the owner could also just press Send there.", nodes: ["agent", "outbox", "mail", "gmail", "graph"], links: ["agent-outbox", "outbox-mail", "mail-gmail", "mail-graph"] },
      { text: "The agent pauses (interrupt). Its full state is saved in Neon as a LangGraph checkpoint, so nothing is lost when the server sleeps.", nodes: ["agent", "checkpoints"], links: ["agent-checkpoints"] },
      { text: "push: the backend signs a Web Push message; Google/Apple's push service delivers '🟡 Approve reply to Mike' with Send / Decline.", nodes: ["outbox", "push", "fcm", "phone"], links: ["outbox-push", "push-fcm", "fcm-phone"] },
      { text: "The owner taps Send. The service worker posts the one-time key to /api/push/act (no login needed: the key IS the permission, valid once, for 48 h).", nodes: ["phone", "edge", "next", "api"], links: ["phone-edge", "edge-proxy", "proxy-next", "next-api"] },
      { text: "The backend resumes the paused run from its checkpoint, sends the reply in the thread, removes the draft and turns the color green.", nodes: ["api", "agent", "checkpoints", "outbox", "mail", "gmail", "customer"], links: ["api-agent", "agent-checkpoints", "agent-outbox", "outbox-mail", "mail-gmail"] },
    ],
  },
  {
    id: "login",
    title: "🔐 Sign in and company isolation",
    summary: "How a request proves who it is and why one company never sees another's data.",
    steps: [
      { text: "The owner opens events.tmalikov.com: GoDaddy's CNAME points to Vercel, which serves it over HTTPS.", nodes: ["laptop", "dns", "edge"], links: ["laptop-edge", "dns-edge"] },
      { text: "proxy.ts asks Clerk: signed in? In a company? If not, it redirects to sign-in or 'choose company'.", nodes: ["edge", "proxy", "clerk"], links: ["edge-proxy", "proxy-clerk"] },
      { text: "Sign-in with Google, Microsoft or email + password happens in Clerk's UI. A Clerk organization = one company.", nodes: ["next", "clerk"], links: ["next-clerk", "proxy-next"] },
      { text: "Every API call carries Clerk's short-lived signed token. Next.js forwards /api/* to the backend on the same domain.", nodes: ["next", "api"], links: ["next-api"] },
      { text: "The backend verifies the token's signature with Clerk's public keys and reads the company and role ONLY from it.", nodes: ["api", "clerk"], links: ["api-clerk"] },
      { text: "Every database query is filtered by that company. Tests (test_isolation.py) try to read and change other companies' data and must fail.", nodes: ["api", "tables"], links: ["api-tables"] },
    ],
  },
  {
    id: "connect",
    title: "🔗 Connect Gmail or Outlook",
    summary: "An admin links the company inbox once; after that the AI watches it.",
    steps: [
      { text: "In Settings an admin clicks Connect Gmail or Connect Outlook. The backend creates a signed 'state' tied to this user and company (stops forged sign-ins).", nodes: ["laptop", "next", "api"], links: ["laptop-edge", "next-api"] },
      { text: "The browser goes to Google's or Microsoft's own consent screen; the owner approves read, draft, label and send.", nodes: ["laptop", "goauth", "entra"], links: [] },
      { text: "Google/Microsoft send the owner back to /gmail/callback or /outlook/callback; the backend exchanges the one-time code for tokens.", nodes: ["next", "api", "mail", "goauth", "entra"], links: ["next-api", "mail-goauth", "mail-entra"] },
      { text: "The long-lived refresh token is encrypted (Fernet) and stored in the mailboxes table. An address can belong to only one company.", nodes: ["api", "tables"], links: ["api-tables"] },
      { text: "From now on the scheduled check reads this inbox. Emails from before connecting are never answered.", nodes: ["qstash", "api", "mail", "gmail", "graph"], links: ["qstash-api", "api-mail", "mail-gmail", "mail-graph"] },
    ],
  },
  {
    id: "deploy",
    title: "🚀 Code to production",
    summary: "How a change gets from the laptop to events.tmalikov.com.",
    steps: [
      { text: "Code is written and tested locally with Docker Compose (Postgres + pgvector, backend, frontend) and the automated test suites.", nodes: ["docker"], links: [] },
      { text: "Committed to GitHub (branch product).", nodes: ["github"], links: [] },
      { text: "vercel deploy --prod builds both projects: Python (FastAPI) and Next.js, pinned to iad1, next to the database.", nodes: ["github", "next", "api"], links: ["github-next", "github-api"] },
      { text: "Neon, Clerk and Upstash were added from the Vercel Marketplace, which puts their keys into the projects' environment variables automatically.", nodes: ["tables", "clerk", "qstash"], links: [] },
      { text: "GoDaddy's CNAME sends events.tmalikov.com to the new deployment.", nodes: ["dns", "edge", "proxy"], links: ["dns-edge", "edge-proxy"] },
    ],
  },
];

// ---------------------------------------------------------------- AI agent (LangGraph)

export const AGENT_ITEMS: Item[] = [
  { id: "start", x: 0, y: 160, icon: "▶️", kind: "code", title: "START", tech: "A new email",
    what: "Called once per saved email, with the company id, so every lookup stays inside that company." },
  { id: "understand", x: 260, y: 160, icon: "💬", kind: "ai", title: "understand", tech: "Chat model · structured output",
    what: "Reads the email and returns: category (info, inquiry, booking, complaint, refund, other), guest count, weekend or not, budget, one-line summary." },
  { id: "look_up", x: 520, y: 160, icon: "📚", kind: "data", title: "look_up", tech: "SQL + RAG",
    what: "Rooms with capacities and minimum prices from the database, plus the 3 policies closest in meaning (pgvector)." },
  { id: "draft", x: 780, y: 160, icon: "✍️", kind: "ai", title: "draft", tech: "Chat model · facts only",
    what: "Writes the reply using ONLY those facts, and also reports what it quoted (prices, guests, dates) so code can check it. Never confirms a booking or decides a refund." },
  { id: "traffic", x: 1040, y: 160, icon: "🚦", kind: "vercel", title: "traffic_light", tech: "Plain code rules, no AI",
    what: "RED: complaint/refund, more guests than the biggest room, a price below the minimum. YELLOW: any price, a date commitment, a missing fact, or a category not on the owner's auto-send list. Otherwise GREEN.",
    facts: ["When unsure: wait for the owner", "Red because of a wrong fact = no ready-to-send draft", "The owner chooses which categories may auto-send"] },
  { id: "send", x: 1300, y: 0, icon: "📤", kind: "vercel", title: "send", tech: "From the company's mailbox",
    what: "Sends in the same thread, removes our draft, sets the green color. Errors are saved on the email with a Retry button." },
  { id: "stage", x: 1300, y: 320, icon: "📝", kind: "vercel", title: "stage", tech: "Draft + color + phone ping",
    what: "Puts the draft in the Gmail/Outlook thread, colors it yellow or red, pings the owner's phone. Done in its own step because code before interrupt() re-runs on resume." },
  { id: "review", x: 1560, y: 320, icon: "⏸️", kind: "data", title: "owner_review", tech: "interrupt() · checkpoint in Neon",
    what: "The run pauses here for minutes or days. It resumes with the owner's decision: approve (optionally edited), sent from Gmail/Outlook, or reject." },
  { id: "mark", x: 1820, y: 200, icon: "✅", kind: "vercel", title: "mark_sent", tech: "Owner pressed Send in the mailbox",
    what: "Already delivered by the owner: we only record it (and their edits, for learning later) and color it green. Never sent twice." },
  { id: "discard", x: 1820, y: 440, icon: "🗑️", kind: "vercel", title: "discard", tech: "Declined",
    what: "Removes our draft and color. The customer's email is left untouched." },
  { id: "end", x: 2080, y: 160, icon: "⏹️", kind: "code", title: "END", tech: "Status saved",
    what: "sent_automatically, sent_after_approval or rejected, with the color, reasons and final text kept for the owner and for future learning." },
];

export const AGENT_LINKS: Link[] = [
  { id: "a1", from: "start", to: "understand" },
  { id: "a2", from: "understand", to: "look_up" },
  { id: "a3", from: "look_up", to: "draft" },
  { id: "a4", from: "draft", to: "traffic" },
  { id: "a5", from: "traffic", to: "send", label: "🟢 green" },
  { id: "a6", from: "traffic", to: "stage", label: "🟡 / 🔴" },
  { id: "a7", from: "stage", to: "review" },
  { id: "a8", from: "review", to: "send", label: "approve / edit" },
  { id: "a9", from: "review", to: "mark", label: "sent from mailbox" },
  { id: "a10", from: "review", to: "discard", label: "decline" },
  { id: "a11", from: "send", to: "end" },
  { id: "a12", from: "mark", to: "end" },
  { id: "a13", from: "discard", to: "end" },
];

// ---------------------------------------------------------------- Database

export type Table = { id: string; x: number; y: number; title: string; note: string; cols: string[] };

export const TABLES: Table[] = [
  { id: "companies", x: 0, y: 220, title: "companies", note: "One Clerk organization",
    cols: ["id PK", "clerk_org_id UNIQUE", "name", "green_categories JSON"] },
  { id: "rooms", x: 380, y: 0, title: "rooms", note: "Prices the rules check against",
    cols: ["id PK", "company_id FK", "name", "capacity", "weekday_min", "weekend_min"] },
  { id: "policies", x: 760, y: 0, title: "policies", note: "RAG knowledge",
    cols: ["id PK", "company_id FK", "text", "embedding vector(1536)"] },
  { id: "mailboxes", x: 380, y: 300, title: "mailboxes", note: "One connected inbox per company",
    cols: ["id PK", "company_id FK UNIQUE", "provider gmail|outlook", "email_address UNIQUE", "refresh_token_enc 🔒", "history_id (position)", "label_ids JSON", "status · last_error"] },
  { id: "messages", x: 760, y: 300, title: "messages", note: "Every email and what happened",
    cols: ["id PK", "company_id FK", "mailbox_id FK", "external_id · thread", "from · subject · body", "category · color · reasons", "draft · final_reply", "status", "thread_id → checkpoint", "was_edited (learning)"] },
  { id: "pushsubs", x: 380, y: 700, title: "push_subscriptions", note: "Phones with notifications on",
    cols: ["id PK", "company_id FK", "user_id", "endpoint UNIQUE", "p256dh · auth"] },
  { id: "ckpt", x: 1140, y: 300, title: "checkpoints (LangGraph)", note: "Paused agent runs",
    cols: ["thread_id", "checkpoint (state)", "checkpoint_blobs", "checkpoint_writes"] },
];

export const TABLE_LINKS: Link[] = [
  { id: "t1", from: "companies", to: "rooms", label: "1 : many" },
  { id: "t2", from: "companies", to: "policies", label: "1 : many" },
  { id: "t3", from: "companies", to: "mailboxes", label: "1 : 1" },
  { id: "t4", from: "companies", to: "messages", label: "1 : many" },
  { id: "t5", from: "companies", to: "pushsubs", label: "1 : many" },
  { id: "t6", from: "mailboxes", to: "messages", label: "1 : many" },
  { id: "t7", from: "messages", to: "ckpt", label: "thread_id" },
];

// ---------------------------------------------------------------- Stack table

export const STACK: { name: string; role: string; plan: string }[] = [
  { name: "Vercel", role: "Hosts the Next.js frontend and the FastAPI backend (serverless), HTTPS, CDN, daily cron", plan: "Hobby (free)" },
  { name: "Neon", role: "Postgres + pgvector: business data, policy vectors, LangGraph checkpoints", plan: "Free" },
  { name: "Clerk", role: "Sign-in (Google, Microsoft, email) and organizations = companies", plan: "Free (dev instance)" },
  { name: "OpenAI", role: "gpt-4.1-mini (understand + draft), text-embedding-3-small (RAG)", plan: "Pay per use" },
  { name: "Upstash QStash", role: "Calls the mail check every 15 minutes", plan: "Free" },
  { name: "Google Cloud", role: "OAuth client + Gmail API (Pub/Sub built but off)", plan: "Free (testing mode)" },
  { name: "Microsoft Entra", role: "OAuth app for Outlook / Microsoft Graph", plan: "Free" },
  { name: "Web Push (FCM / Apple)", role: "Delivers phone notifications", plan: "Free" },
  { name: "GoDaddy", role: "tmalikov.com domain, CNAME for events.", plan: "Domain" },
  { name: "GitHub + Docker", role: "Code (branch product) and the local copy for development and tests", plan: "Free" },
];

export const NOT_USED: { name: string; why: string }[] = [
  { name: "Render", why: "Considered for the backend; too slow to wake up on first visit, so everything runs on Vercel." },
  { name: "Google Pub/Sub", why: "Instant Gmail push is built in but switched off: it needs a Google billing account. The 15-minute schedule covers it." },
  { name: "Neo4j / a separate vector DB", why: "Not needed yet: facts and vectors live in Postgres (pgvector). A graph database only if questions really need many hops across facts." },
  { name: "Native mobile app", why: "The installed web app (PWA) gives notifications with Send / Decline on Android and iPhone. A store app only if pilot owners ask for it." },
];
