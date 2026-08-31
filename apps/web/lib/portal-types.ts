export type PortalRole = "patient" | "dentist" | "admin";

export type PortalUser = {
  access_token: string;
  token_type: string;
  role: PortalRole;
  user_id: string;
  name: string;
  email: string;
  first_name: string;
  last_name: string;
  profile_image: string;
};

export type RegisterPayload = {
  first_name: string;
  last_name: string;
  email: string;
  password: string;
  phone: string;
  location: string;
  profile_image?: string | null;
  degree?: string;
  degree_year?: number;
  institution?: string;
  specialized_training?: string;
};

export type PortalMeta = {
  title: string;
  heroLine: string;
  subtitle: string;
  eyebrow: string;
  features: string[];
  accentVar: string;
  glowVar: string;
};

export const PORTAL_META: Record<PortalRole, PortalMeta> = {
  patient: {
    eyebrow: "Patient access",
    title: "Your oral health",
    heroLine: "hub.",
    subtitle:
      "Register to save scans, chat with your AI dentist, and get matched with local care.",
    features: ["Scan history", "AI chat memory", "Product picks", "Dentist matching"],
    accentVar: "var(--accent)",
    glowVar: "var(--accent-glow)",
  },
  dentist: {
    eyebrow: "Dentist partner",
    title: "Grow your",
    heroLine: "practice.",
    subtitle:
      "List products, receive referrals, and connect with patients who need your expertise.",
    features: ["Product catalog", "Order alerts", "Patient referrals", "AI descriptions"],
    accentVar: "var(--violet)",
    glowVar: "var(--violet-glow)",
  },
  admin: {
    eyebrow: "Platform admin",
    title: "Run the",
    heroLine: "platform.",
    subtitle:
      "Oversee users, verify dentists, and manage marketplace operations across DantShaant.",
    features: ["User management", "Dentist verification", "Analytics", "RAG knowledge"],
    accentVar: "var(--warn)",
    glowVar: "rgba(245, 185, 66, 0.35)",
  },
};
