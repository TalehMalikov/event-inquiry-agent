// Everything the /architecture page draws. Short on purpose: cards show a name, details appear on tap.
// Positions are diagram pixels; children are relative to their group.

export type Kind = "person" | "vercel" | "ext" | "data" | "ai" | "off" | "code";

export type Info = {
  title: string;
  tech: string; // one short line, shown in the details panel
  icon: string;
  kind: Kind;
  what: string; // one or two sentences
  code?: string[];
};

export type Box = { id: string; label: string; x: number; y: number; w: number; h: number; tone: string };
export type Item = Info & { id: string; parent?: string; x: number; y: number };
export type Link = { id: string; from: string; to: string; label?: string; off?: boolean };
export type Step = { text: string; nodes: string[]; links: string[] };
export type Flow = { id: string; title: string; steps: Step[] };

// Layout grid: cards 180×56, 70 px apart inside groups
const row = (i: number) => 40 + i * 70;
const tall = (n: number) => 42 + n * 70;

// ---------------------------------------------------------------- System map

export const SYSTEM_BOXES: Box[] = [
  { id: "g-people", label: "People", x: 0, y: 0, w: 220, h: tall(3), tone: "slate" },
  { id: "g-dev", label: "Code", x: 0, y: 300, w: 220, h: tall(2), tone: "slate" },
  { id: "g-net", label: "Domain", x: 260, y: 0, w: 220, h: tall(2), tone: "slate" },
  { id: "g-vercel", label: "Vercel", x: 520, y: 0, w: 440, h: tall(6), tone: "zinc" },
  { id: "g-upstash", label: "Upstash", x: 520, y: 510, w: 220, h: tall(1), tone: "emerald" },
  { id: "g-clerk", label: "Clerk", x: 1000, y: 0, w: 220, h: tall(1), tone: "violet" },
  { id: "g-openai", label: "OpenAI", x: 1000, y: 150, w: 220, h: tall(2), tone: "teal" },
  { id: "g-neon", label: "Neon Postgres", x: 1000, y: 370, w: 220, h: tall(3), tone: "sky" },
  { id: "g-google", label: "Google", x: 1260, y: 0, w: 220, h: tall(3), tone: "amber" },
  { id: "g-ms", label: "Microsoft", x: 1260, y: 290, w: 220, h: tall(2), tone: "blue" },
  { id: "g-push", label: "Push", x: 1260, y: 510, w: 220, h: tall(1), tone: "rose" },
];

export const SYSTEM_ITEMS: Item[] = [
  { id: "customer", parent: "g-people", x: 20, y: row(0), icon: "✉️", kind: "person", title: "Customer",
    tech: "Any email app", what: "Emails the venue. Only ever sees a normal reply: never colors or reasons." },
  { id: "phone", parent: "g-people", x: 20, y: row(1), icon: "📱", kind: "person", title: "Owner's phone",
    tech: "Installed app + service worker", what: "Gets the colored ping. Send / Decline work right from the notification.",
    code: ["public/sw.js"] },
  { id: "laptop", parent: "g-people", x: 20, y: row(2), icon: "💻", kind: "person", title: "Owner's browser",
    tech: "events.tmalikov.com", what: "Inbox, approve screen, company data, settings." },

  { id: "github", parent: "g-dev", x: 20, y: row(0), icon: "🐙", kind: "code", title: "GitHub",
    tech: "Branch product", what: "The code. Deployed with the Vercel CLI." },
  { id: "docker", parent: "g-dev", x: 20, y: row(1), icon: "🐳", kind: "code", title: "Docker",
    tech: "Local copy", what: "Runs everything on a laptop for development and tests." },

  { id: "dns", parent: "g-net", x: 20, y: row(0), icon: "🌐", kind: "ext", title: "GoDaddy DNS",
    tech: "CNAME events", what: "Points events.tmalikov.com at Vercel." },
  { id: "edge", parent: "g-net", x: 20, y: row(1), icon: "🛡️", kind: "vercel", title: "Vercel Edge",
    tech: "HTTPS + CDN", what: "Secure connection and fast static files." },

  { id: "proxy", parent: "g-vercel", x: 20, y: row(0), icon: "🚦", kind: "vercel", title: "proxy.ts",
    tech: "Login gate", what: "Sends signed-out visitors to sign-in before any page loads.", code: ["frontend/src/proxy.ts"] },
  { id: "next", parent: "g-vercel", x: 20, y: row(1), icon: "▲", kind: "vercel", title: "Next.js app",
    tech: "Frontend", what: "All screens. Forwards /api calls to the backend on the same domain.", code: ["frontend/src/app/"] },
  { id: "cron", parent: "g-vercel", x: 20, y: row(5), icon: "⏰", kind: "vercel", title: "Vercel Cron",
    tech: "Daily backup", what: "Runs the mail check once a day, just in case." },
  { id: "api", parent: "g-vercel", x: 240, y: row(0), icon: "⚡", kind: "vercel", title: "FastAPI",
    tech: "Backend · Python", what: "Checks the login token and takes the company only from it. One company never sees another's data.",
    code: ["backend/app/main.py", "backend/app/auth.py"] },
  { id: "mail", parent: "g-vercel", x: 240, y: row(1), icon: "📬", kind: "vercel", title: "Mail connectors",
    tech: "Gmail + Outlook", what: "Reads new mail, skips newsletters and robots, drafts, colors and sends in the thread.",
    code: ["gmail.py", "outlook.py"] },
  { id: "agent", parent: "g-vercel", x: 240, y: row(2), icon: "🧠", kind: "ai", title: "LangGraph agent",
    tech: "The traffic light", what: "Drafts every reply, then decides: send now or wait for the owner.", code: ["agent.py"] },
  { id: "rag", parent: "g-vercel", x: 240, y: row(3), icon: "📚", kind: "ai", title: "RAG",
    tech: "Policy search", what: "Finds the company's own policies that match the email.", code: ["rag.py"] },
  { id: "outbox", parent: "g-vercel", x: 240, y: row(4), icon: "📤", kind: "vercel", title: "Outbox",
    tech: "Drafts + colors", what: "Puts drafts and colors in the mailbox; sends once when approved.", code: ["outbox.py"] },
  { id: "push", parent: "g-vercel", x: 240, y: row(5), icon: "🔔", kind: "vercel", title: "Web Push",
    tech: "Phone pings", what: "Sends '🟡 Approve reply to Mike' to the owner's devices.", code: ["push.py"] },

  { id: "qstash", parent: "g-upstash", x: 20, y: row(0), icon: "⏱️", kind: "ext", title: "QStash",
    tech: "Every 15 min", what: "Calls the mail check every 15 minutes." },
  { id: "clerk", parent: "g-clerk", x: 20, y: row(0), icon: "🔐", kind: "ext", title: "Clerk",
    tech: "Login + companies", what: "Google, Microsoft or email login. Each organization is one company." },
  { id: "llm", parent: "g-openai", x: 20, y: row(0), icon: "💬", kind: "ai", title: "GPT-4.1 mini",
    tech: "Chat model", what: "Understands the email, then writes the draft." },
  { id: "embed", parent: "g-openai", x: 20, y: row(1), icon: "🔢", kind: "ai", title: "Embeddings",
    tech: "text-embedding-3-small", what: "Turns text into vectors for search by meaning." },
  { id: "tables", parent: "g-neon", x: 20, y: row(0), icon: "🗄️", kind: "data", title: "Tables",
    tech: "Business data", what: "Companies, rooms, emails, mailboxes. Every row belongs to one company.", code: ["db.py"] },
  { id: "vector", parent: "g-neon", x: 20, y: row(1), icon: "🧭", kind: "data", title: "pgvector",
    tech: "Vector search", what: "Policy vectors, in the same database." },
  { id: "checkpoints", parent: "g-neon", x: 20, y: row(2), icon: "⏸️", kind: "data", title: "Checkpoints",
    tech: "Paused runs", what: "Saved agent state, so a run waits hours for the owner and then continues." },
  { id: "goauth", parent: "g-google", x: 20, y: row(0), icon: "🔑", kind: "ext", title: "Google login",
    tech: "OAuth", what: "Owner allows read, draft, label and send." },
  { id: "gmail", parent: "g-google", x: 20, y: row(1), icon: "📧", kind: "ext", title: "Gmail API",
    tech: "Mail + labels", what: "Where Gmail companies' mail lives." },
  { id: "pubsub", parent: "g-google", x: 20, y: row(2), icon: "📡", kind: "off", title: "Pub/Sub (off)",
    tech: "Instant push", what: "Built but off: needs Google billing. QStash covers it." },
  { id: "entra", parent: "g-ms", x: 20, y: row(0), icon: "🔑", kind: "ext", title: "Microsoft login",
    tech: "OAuth", what: "Owner allows read, draft, categories and send." },
  { id: "graph", parent: "g-ms", x: 20, y: row(1), icon: "📨", kind: "ext", title: "Outlook (Graph)",
    tech: "Mail + categories", what: "Where Outlook companies' mail lives." },
  { id: "fcm", parent: "g-push", x: 20, y: row(0), icon: "📲", kind: "ext", title: "FCM / Apple",
    tech: "Push delivery", what: "Delivers the ping to the phone, even when the app is closed." },
];

export const SYSTEM_LINKS: Link[] = [
  { id: "cust-gmail", from: "customer", to: "gmail", label: "email" },
  { id: "cust-graph", from: "customer", to: "graph", label: "email" },
  { id: "dns-edge", from: "dns", to: "edge" },
  { id: "laptop-edge", from: "laptop", to: "edge" },
  { id: "phone-edge", from: "phone", to: "edge" },
  { id: "edge-proxy", from: "edge", to: "proxy" },
  { id: "proxy-clerk", from: "proxy", to: "clerk", label: "signed in?" },
  { id: "proxy-next", from: "proxy", to: "next" },
  { id: "next-clerk", from: "next", to: "clerk", label: "login" },
  { id: "next-api", from: "next", to: "api", label: "/api" },
  { id: "api-clerk", from: "api", to: "clerk", label: "verify" },
  { id: "api-tables", from: "api", to: "tables", label: "SQL" },
  { id: "qstash-api", from: "qstash", to: "api", label: "15 min" },
  { id: "cron-api", from: "cron", to: "api", label: "daily" },
  { id: "api-mail", from: "api", to: "mail" },
  { id: "mail-gmail", from: "mail", to: "gmail" },
  { id: "mail-graph", from: "mail", to: "graph" },
  { id: "mail-goauth", from: "mail", to: "goauth", label: "tokens" },
  { id: "mail-entra", from: "mail", to: "entra", label: "tokens" },
  { id: "gmail-pubsub", from: "gmail", to: "pubsub", off: true },
  { id: "api-agent", from: "api", to: "agent" },
  { id: "agent-llm", from: "agent", to: "llm" },
  { id: "agent-rag", from: "agent", to: "rag" },
  { id: "rag-embed", from: "rag", to: "embed" },
  { id: "rag-vector", from: "rag", to: "vector" },
  { id: "agent-checkpoints", from: "agent", to: "checkpoints", label: "pause" },
  { id: "agent-outbox", from: "agent", to: "outbox" },
  { id: "outbox-mail", from: "outbox", to: "mail" },
  { id: "outbox-push", from: "outbox", to: "push" },
  { id: "push-fcm", from: "push", to: "fcm" },
  { id: "fcm-phone", from: "fcm", to: "phone", label: "ping" },
  { id: "github-next", from: "github", to: "next", label: "deploy" },
  { id: "github-api", from: "github", to: "api" },
];

export const FLOWS: Flow[] = [
  {
    id: "green",
    title: "🟢 Answered automatically",
    steps: [
      { text: "Customer emails the venue", nodes: ["customer", "gmail", "graph"], links: ["cust-gmail", "cust-graph"] },
      { text: "QStash triggers the mail check", nodes: ["qstash", "api"], links: ["qstash-api"] },
      { text: "New mail is fetched, robots skipped", nodes: ["api", "mail", "gmail", "graph"], links: ["api-mail", "mail-gmail", "mail-graph"] },
      { text: "Saved, agent starts", nodes: ["api", "tables", "agent"], links: ["api-tables", "api-agent"] },
      { text: "AI reads the email", nodes: ["agent", "llm"], links: ["agent-llm"] },
      { text: "Prices + policies looked up", nodes: ["agent", "rag", "embed", "vector", "tables"], links: ["agent-rag", "rag-embed", "rag-vector"] },
      { text: "AI writes the draft", nodes: ["agent", "llm"], links: ["agent-llm"] },
      { text: "Rules say green", nodes: ["agent"], links: [] },
      { text: "Sent in the thread, labeled green", nodes: ["agent", "outbox", "mail", "gmail", "graph"], links: ["agent-outbox", "outbox-mail", "mail-gmail", "mail-graph"] },
    ],
  },
  {
    id: "yellow",
    title: "🟡 Owner taps Send",
    steps: [
      { text: "Booking request is drafted", nodes: ["customer", "gmail", "mail", "api", "agent", "llm", "rag"], links: ["cust-gmail", "api-mail", "mail-gmail", "api-agent", "agent-llm", "agent-rag"] },
      { text: "Rules say yellow (price)", nodes: ["agent"], links: [] },
      { text: "Draft + yellow color in the mailbox", nodes: ["agent", "outbox", "mail", "gmail", "graph"], links: ["agent-outbox", "outbox-mail", "mail-gmail", "mail-graph"] },
      { text: "Agent pauses, state saved", nodes: ["agent", "checkpoints"], links: ["agent-checkpoints"] },
      { text: "Ping reaches the phone", nodes: ["outbox", "push", "fcm", "phone"], links: ["outbox-push", "push-fcm", "fcm-phone"] },
      { text: "Owner taps Send", nodes: ["phone", "edge", "proxy", "next", "api"], links: ["phone-edge", "edge-proxy", "proxy-next", "next-api"] },
      { text: "Agent resumes and sends", nodes: ["api", "agent", "checkpoints", "outbox", "mail", "gmail"], links: ["api-agent", "agent-checkpoints", "agent-outbox", "outbox-mail", "mail-gmail"] },
    ],
  },
  {
    id: "login",
    title: "🔐 Sign in",
    steps: [
      { text: "Owner opens the site", nodes: ["laptop", "dns", "edge"], links: ["laptop-edge", "dns-edge"] },
      { text: "Gate checks the login", nodes: ["edge", "proxy", "clerk"], links: ["edge-proxy", "proxy-clerk"] },
      { text: "Clerk signs them in", nodes: ["next", "clerk"], links: ["next-clerk", "proxy-next"] },
      { text: "Backend verifies the token", nodes: ["next", "api", "clerk"], links: ["next-api", "api-clerk"] },
      { text: "Only that company's data", nodes: ["api", "tables"], links: ["api-tables"] },
    ],
  },
  {
    id: "connect",
    title: "🔗 Connect inbox",
    steps: [
      { text: "Admin clicks Connect", nodes: ["laptop", "next", "api"], links: ["laptop-edge", "next-api"] },
      { text: "Google / Microsoft asks permission", nodes: ["mail", "goauth", "entra"], links: ["mail-goauth", "mail-entra"] },
      { text: "Token stored encrypted", nodes: ["api", "tables"], links: ["api-tables"] },
      { text: "Inbox checked from now on", nodes: ["qstash", "api", "mail", "gmail", "graph"], links: ["qstash-api", "api-mail", "mail-gmail", "mail-graph"] },
    ],
  },
  {
    id: "deploy",
    title: "🚀 Deploy",
    steps: [
      { text: "Tested locally", nodes: ["docker"], links: [] },
      { text: "Pushed to GitHub", nodes: ["github"], links: [] },
      { text: "Vercel builds front + back", nodes: ["github", "next", "api"], links: ["github-next", "github-api"] },
      { text: "Live on events.tmalikov.com", nodes: ["dns", "edge", "proxy"], links: ["dns-edge", "edge-proxy"] },
    ],
  },
];

// ---------------------------------------------------------------- AI agent (LangGraph)

export const AGENT_ITEMS: Item[] = [
  { id: "start", x: 0, y: 120, icon: "▶️", kind: "code", title: "New email", tech: "Start", what: "One run per email." },
  { id: "understand", x: 230, y: 120, icon: "💬", kind: "ai", title: "understand", tech: "AI",
    what: "Category, guests, date, budget." },
  { id: "look_up", x: 460, y: 120, icon: "📚", kind: "data", title: "look_up", tech: "Database + RAG",
    what: "Rooms, prices and matching policies." },
  { id: "draft", x: 690, y: 120, icon: "✍️", kind: "ai", title: "draft", tech: "AI",
    what: "Writes the reply from those facts only." },
  { id: "traffic", x: 920, y: 120, icon: "🚦", kind: "vercel", title: "traffic light", tech: "Code rules, no AI",
    what: "🔴 complaint, refund or a wrong fact. 🟡 a price, a date, a missing fact. 🟢 everything else." },
  { id: "send", x: 1150, y: 0, icon: "📤", kind: "vercel", title: "send", tech: "In the thread",
    what: "Sends once, labels green." },
  { id: "stage", x: 1150, y: 240, icon: "📝", kind: "vercel", title: "stage", tech: "Draft + ping",
    what: "Draft and color in the mailbox, ping to the phone." },
  { id: "review", x: 1380, y: 240, icon: "⏸️", kind: "data", title: "owner review", tech: "Paused",
    what: "Waits for the owner, minutes or days." },
  { id: "mark", x: 1610, y: 160, icon: "✅", kind: "vercel", title: "mark sent", tech: "Sent from mailbox",
    what: "Owner pressed Send in Gmail/Outlook: just recorded." },
  { id: "discard", x: 1610, y: 320, icon: "🗑️", kind: "vercel", title: "discard", tech: "Declined",
    what: "Draft and color removed." },
  { id: "end", x: 1840, y: 120, icon: "⏹️", kind: "code", title: "Done", tech: "End", what: "Result saved." },
];

export const AGENT_LINKS: Link[] = [
  { id: "a1", from: "start", to: "understand" },
  { id: "a2", from: "understand", to: "look_up" },
  { id: "a3", from: "look_up", to: "draft" },
  { id: "a4", from: "draft", to: "traffic" },
  { id: "a5", from: "traffic", to: "send", label: "🟢" },
  { id: "a6", from: "traffic", to: "stage", label: "🟡🔴" },
  { id: "a7", from: "stage", to: "review" },
  { id: "a8", from: "review", to: "send", label: "approve" },
  { id: "a9", from: "review", to: "mark", label: "sent in mailbox" },
  { id: "a10", from: "review", to: "discard", label: "decline" },
  { id: "a11", from: "send", to: "end" },
  { id: "a12", from: "mark", to: "end" },
  { id: "a13", from: "discard", to: "end" },
];

// ---------------------------------------------------------------- Database

export type Table = { id: string; x: number; y: number; title: string; note: string; cols: string[] };

export const TABLES: Table[] = [
  { id: "companies", x: 0, y: 170, title: "companies", note: "One per Clerk organization", cols: ["clerk_org_id", "name", "auto-send rules"] },
  { id: "rooms", x: 300, y: 0, title: "rooms", note: "Capacity and minimum prices", cols: ["company_id", "capacity", "min prices"] },
  { id: "policies", x: 600, y: 0, title: "policies", note: "What RAG searches", cols: ["company_id", "text", "embedding"] },
  { id: "mailboxes", x: 300, y: 200, title: "mailboxes", note: "One connected inbox per company", cols: ["company_id", "gmail | outlook", "token 🔒"] },
  { id: "messages", x: 600, y: 200, title: "messages", note: "Every email and what happened to it", cols: ["company_id", "email", "color", "reply", "status"] },
  { id: "pushsubs", x: 300, y: 400, title: "push_subscriptions", note: "Phones with notifications on", cols: ["company_id", "device"] },
  { id: "ckpt", x: 900, y: 200, title: "checkpoints", note: "Paused agent runs (LangGraph)", cols: ["thread_id", "state"] },
];

export const TABLE_LINKS: Link[] = [
  { id: "t1", from: "companies", to: "rooms" },
  { id: "t2", from: "companies", to: "policies" },
  { id: "t3", from: "companies", to: "mailboxes" },
  { id: "t4", from: "companies", to: "messages" },
  { id: "t5", from: "companies", to: "pushsubs" },
  { id: "t6", from: "mailboxes", to: "messages" },
  { id: "t7", from: "messages", to: "ckpt" },
];

// ---------------------------------------------------------------- Services

export const STACK: { name: string; role: string; plan: string }[] = [
  { name: "Vercel", role: "Hosts frontend + backend", plan: "Free" },
  { name: "Neon", role: "Database + vectors", plan: "Free" },
  { name: "Clerk", role: "Login + companies", plan: "Free" },
  { name: "OpenAI", role: "Understand, draft, embeddings", plan: "Pay per use" },
  { name: "Upstash QStash", role: "15-minute mail check", plan: "Free" },
  { name: "Google Cloud", role: "Gmail access", plan: "Free" },
  { name: "Microsoft Entra", role: "Outlook access", plan: "Free" },
  { name: "FCM / Apple Push", role: "Phone pings", plan: "Free" },
  { name: "GoDaddy", role: "Domain", plan: "Paid domain" },
  { name: "GitHub + Docker", role: "Code + local copy", plan: "Free" },
];

export const NOT_USED: { name: string; why: string }[] = [
  { name: "Render", why: "Too slow to wake up." },
  { name: "Google Pub/Sub", why: "Needs billing. Built, switched off." },
  { name: "Neo4j", why: "Postgres is enough for now." },
  { name: "Native app", why: "The installed web app does the job." },
];
