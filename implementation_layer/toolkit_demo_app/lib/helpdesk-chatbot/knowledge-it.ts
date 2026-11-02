// The second Helpdesk Chatbot example: the internal IT and HR helpdesk of a
// fictional company. All of it is synthetic. It uses the same three shapes as
// the AI hub (services, FAQ articles, teams), so the same chat, tools and search
// work on it unchanged. The "services" are requests an employee can make, with a
// price (who pays) and a duration (how long it takes).

import type { Article, Knowledge, Service } from "./knowledge";

const SERVICES: Service[] = [
  {
    id: "password-reset",
    name: "Password reset and account unlock",
    category: "accounts-access",
    audiences: ["employee", "manager", "new-hire"],
    summary:
      "Reset your password or unlock your account yourself in about two minutes.",
    details:
      "Use the self-service portal and approve the sign-in on your authenticator app. Accounts lock after 5 failed attempts and unlock by themselves after 30 minutes. If you have lost your phone, call the service desk with your employee number.",
    price: "Free",
    duration: "About 2 minutes (self-service)",
    team: "it-service-desk",
    tags: ["password", "locked out", "unlock", "login", "account", "salasana"],
  },
  {
    id: "mfa-setup",
    name: "Multi-factor authentication setup",
    category: "accounts-access",
    audiences: ["employee", "manager", "new-hire"],
    summary: "Set up the authenticator app that confirms your sign-ins.",
    details:
      "Install the company authenticator app on your phone, scan the code in the portal and keep the backup codes. A new phone needs a reset by the service desk.",
    price: "Free",
    duration: "10 minutes",
    team: "it-service-desk",
    tags: ["mfa", "2fa", "authenticator", "phone", "sign-in", "verification"],
  },
  {
    id: "vpn-access",
    name: "VPN access",
    category: "accounts-access",
    audiences: ["employee", "manager", "new-hire"],
    summary: "Secure access to company systems from home or while travelling.",
    details:
      "The VPN client is installed on every company laptop and starts after you sign in. Personal computers are not supported. If it keeps disconnecting, try another network or a wired connection and restart the client; if it continues, the service desk can check the connection logs.",
    price: "Free",
    duration: "Same day",
    team: "it-service-desk",
    tags: ["vpn", "remote", "home", "connection", "disconnects", "network"],
  },
  {
    id: "laptop-replacement",
    name: "New or replacement laptop",
    category: "devices",
    audiences: ["employee", "manager"],
    summary:
      "Order a standard laptop, or a replacement if yours is broken or over four years old.",
    details:
      "Standard Windows and Mac laptops are delivered ready to use. Other configurations need your manager's approval. Return the old laptop to the service desk when the new one arrives.",
    price: "Charged to your team's budget (€1,100 for a standard laptop)",
    duration: "5 working days",
    team: "it-service-desk",
    tags: ["laptop", "computer", "broken", "replace", "hardware", "device"],
  },
  {
    id: "new-hire-kit",
    name: "New-hire equipment kit",
    category: "devices",
    audiences: ["new-hire", "manager"],
    summary: "Laptop, phone, headset and accounts, ready on the first day.",
    details:
      "A manager orders the kit at least 10 working days before the start date. On the first day the laptop, phone, headset and accounts are prepared. A late order is treated as a normal laptop request and takes 5 working days.",
    price: "Charged to the hiring team's budget (€1,400)",
    duration: "Ready on day one if ordered 10 working days ahead",
    team: "it-service-desk",
    tags: [
      "new hire",
      "onboarding",
      "first day",
      "equipment",
      "starter",
      "laptop",
      "phone",
    ],
  },
  {
    id: "software-request",
    name: "Software request",
    category: "software",
    audiences: ["employee", "manager"],
    summary:
      "Install an approved app, or ask for software that is not in the catalogue.",
    details:
      "Approved apps install from the self-service app store in a few minutes. Software outside the catalogue needs a security review and your manager's approval; the licence is paid from your team's budget.",
    price: "Free for catalogue apps; licence cost to your team for others",
    duration: "Minutes for catalogue apps; 3–10 working days for a review",
    team: "security",
    tags: ["software", "install", "licence", "app", "tool", "application"],
  },
  {
    id: "report-phishing",
    name: "Report a suspicious email or a lost device",
    category: "security",
    audiences: ["employee", "manager", "new-hire"],
    summary:
      "Tell the security team at once about phishing, a lost laptop or phone, or a possible data leak.",
    details:
      "Press the report button in your mail client or forward the suspicious email to the report address; do not click links or open attachments. For a lost device or a possible leak, call the security hotline at any time. Report early: it is never a problem to report by mistake.",
    price: "Free",
    duration: "Immediate; the team replies within 1 working hour",
    team: "security",
    tags: [
      "phishing",
      "spam",
      "suspicious",
      "lost",
      "stolen",
      "security",
      "incident",
      "leak",
    ],
  },
  {
    id: "leave-request",
    name: "Annual leave and absence",
    category: "people-hr",
    audiences: ["employee", "manager"],
    summary: "Request annual leave or report an absence in the HR system.",
    details:
      "Request leave in the HR system at least two weeks ahead for a week or longer. Your manager approves within 3 working days. Report sick leave to your manager and in the system on the first day.",
    price: "Free",
    duration: "Approved within 3 working days",
    team: "hr-people",
    tags: [
      "leave",
      "vacation",
      "holiday",
      "absence",
      "sick",
      "days off",
      "loma",
    ],
  },
  {
    id: "remote-work",
    name: "Remote work agreement",
    category: "people-hr",
    audiences: ["employee", "manager"],
    summary: "Agree with your manager which days you work from home.",
    details:
      "Up to three days a week at home is standard. Longer arrangements, or working from another country, need a written agreement with HR because of tax and insurance rules.",
    price: "Free",
    duration: "Same week for the standard agreement; 2–4 weeks for abroad",
    team: "hr-people",
    tags: ["remote", "home office", "hybrid", "abroad", "telework"],
  },
  {
    id: "onboarding-plan",
    name: "First-week plan and buddy",
    category: "people-hr",
    audiences: ["new-hire", "manager"],
    summary: "A buddy and a day-by-day plan for the first week.",
    details:
      "HR sends the plan to the new hire and the manager before the first day: access, introductions, the mandatory security training and a buddy to ask questions.",
    price: "Free",
    duration: "The first week",
    team: "hr-people",
    tags: ["onboarding", "buddy", "new hire", "training", "first week"],
  },
];

const ARTICLES: Article[] = [
  {
    id: "who-we-are",
    title: "What is the IT & HR Helpdesk?",
    body: "The IT & HR Helpdesk is the first place Northwind Group employees go with questions about accounts, devices, software, security and working at Northwind. Most answers are here; for the rest, the right team picks up your question.",
    tags: ["about", "helpdesk", "who", "northwind"],
  },
  {
    id: "service-desk-hours",
    title: "Service desk hours and contact",
    body: "The IT Service Desk is open Monday to Friday 7–17 (Finnish time), on the ground floor of the main office and by phone. Urgent security matters can be reported to the security hotline at any time, day and night. HR questions go to the HR People team on weekdays 8–16.",
    tags: ["hours", "open", "contact", "phone", "location", "hotline"],
  },
  {
    id: "first-day",
    title: "What happens on my first day?",
    body: "If you have not received your kit yet, collect it from the service desk. Sign in with your temporary password, set up multi-factor authentication and meet your buddy. Allow about an hour for the account setup. Your manager and HR have already sent you the first-week plan.",
    tags: ["first day", "new hire", "start", "monday", "account", "kit"],
  },
  {
    id: "password-rules",
    title: "Password rules",
    body: "Passwords must be at least 14 characters and are changed once a year. Never share your password, not even with the service desk, which never asks for it. If you suspect someone else knows it, change it at once in the self-service portal and report it to the security team.",
    tags: ["password", "rules", "length", "change", "share"],
  },
  {
    id: "byod",
    title: "Can I use my own phone or laptop for work?",
    body: "Your own phone can be used for email, calendar and the authenticator app once you install the device management app. Personal laptops cannot connect to company systems; use a company laptop.",
    tags: ["personal", "own device", "byod", "phone", "laptop", "private"],
  },
  {
    id: "vpn-tips",
    title: "My VPN disconnects: what can I try?",
    body: "Restart the VPN client, switch between Wi-Fi and a wired connection, and avoid public networks that ask you to sign in on a web page. Check that the laptop has the latest updates. If it still disconnects, contact the service desk with the time of the problem so the connection logs can be checked.",
    tags: ["vpn", "disconnect", "connection", "wifi", "home", "slow"],
  },
  {
    id: "phishing",
    title: "What should I do with a suspicious email?",
    body: "Do not click links or open attachments. Press the report button in your mail client or forward the email to the report address. If you already clicked a link or entered a password, change your password and call the security hotline straight away.",
    tags: ["phishing", "email", "suspicious", "scam", "click", "report"],
  },
  {
    id: "laptop-return",
    title: "What happens to my old equipment?",
    body: "Return company equipment to the service desk on your last day, or when a replacement arrives. Data on returned laptops is wiped. Save work files in the company cloud storage, not on the laptop.",
    tags: ["return", "equipment", "leave", "old laptop", "wipe", "data"],
  },
  {
    id: "security-training",
    title: "Mandatory security training",
    body: "Every employee completes the security training within the first two weeks and again every year. It takes about 45 minutes online and the link is in your first-week plan.",
    tags: ["training", "security", "mandatory", "course", "yearly"],
  },
  {
    id: "chatbot-itself",
    title: "About this chatbot",
    body: "This chatbot is an AI assistant. It answers from the helpdesk's own service list and FAQ, shows which entries it used, and can pass your question to a person. It can make mistakes, so check important details with the team.",
    tags: ["chatbot", "ai assistant", "how it works", "accuracy"],
  },
];

export const IT_KNOWLEDGE: Knowledge = {
  id: "it-hr",
  organisation: "Northwind Group",
  helpdeskName: "Northwind IT & HR Helpdesk",
  persona:
    "the internal helpdesk of Northwind Group, a company of about 600 employees in Finland. It helps employees with accounts, devices, software, security and everyday HR questions",
  scope: "IT and HR matters at work",
  faqTopics:
    "service desk hours, first day, passwords, personal devices, VPN, phishing, returning equipment, security training",
  serviceNoun: "requests and services",
  handoffExample: "I start on Monday and would like to check that ...",
  categories: [
    "accounts-access",
    "devices",
    "software",
    "security",
    "people-hr",
  ],
  categoryLabels: {
    "accounts-access": "Accounts and access",
    devices: "Devices",
    software: "Software",
    security: "Security",
    "people-hr": "People and HR",
  },
  audiences: ["employee", "manager", "new-hire"],
  teams: {
    "it-service-desk": {
      name: "IT Service Desk",
      responseTime: "4 working hours",
      handles: "accounts, passwords, VPN, laptops, phones, general IT problems",
    },
    security: {
      name: "Security team",
      responseTime: "1 working hour",
      handles: "phishing, lost devices, data leaks, software security reviews",
    },
    "hr-people": {
      name: "HR People team",
      responseTime: "1 working day",
      handles: "leave, absences, remote work, onboarding, contracts",
    },
    workplace: {
      name: "Workplace team",
      responseTime: "2 working days",
      handles:
        "desks and office furniture, access badges, parking, office supplies",
    },
  },
  services: SERVICES,
  articles: ARTICLES,
};
