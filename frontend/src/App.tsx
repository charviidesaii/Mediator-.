import { FormEvent, ReactNode, useEffect, useMemo, useState } from "react";
import { apiClient, ApiError } from "./api/client";
import type {
  AlignmentWorkflowResult,
  ConfirmedDecision,
  ConflictCategory,
  ConflictSeverity,
  ConflictType,
  DetectedConflict,
  EvidenceItem,
  ExtractedPerspective,
  MemberResponse,
  Project,
  ProposedResolution,
  SynthesisReport,
  TeamMember,
} from "./api/models";

type Page = "Overview" | "Check-In" | "Alignment" | "Decisions" | "Team Memory";

type IconName =
  | "grid"
  | "check"
  | "network"
  | "spark"
  | "clock"
  | "settings"
  | "bell"
  | "arrow"
  | "plus"
  | "close"
  | "chevron"
  | "message"
  | "calendar"
  | "target";

const paths: Record<IconName, ReactNode> = {
  grid: (
    <>
      <rect x="3" y="3" width="7" height="7" rx="2" />
      <rect x="14" y="3" width="7" height="7" rx="2" />
      <rect x="3" y="14" width="7" height="7" rx="2" />
      <rect x="14" y="14" width="7" height="7" rx="2" />
    </>
  ),
  check: (
    <>
      <path d="M4 12.5 9 17l11-11" />
      <path d="M20 12a8 8 0 1 1-5-7.4" />
    </>
  ),
  network: (
    <>
      <circle cx="12" cy="5" r="2.5" />
      <circle cx="5" cy="18" r="2.5" />
      <circle cx="19" cy="18" r="2.5" />
      <path d="m10.8 7.2-4.6 8.6M13.2 7.2l4.6 8.6M7.5 18h9" />
    </>
  ),
  spark: (
    <path d="m12 2 1.5 6.5L20 10l-6.5 1.5L12 18l-1.5-6.5L4 10l6.5-1.5L12 2Zm7 14 .6 2.4L22 19l-2.4.6L19 22l-.6-2.4L16 19l2.4-.6L19 16Z" />
  ),
  clock: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3.5 2" />
    </>
  ),
  settings: (
    <>
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1a1.7 1.7 0 0 0 1.9.3A1.7 1.7 0 0 0 10 3v-.2h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1Z" />
    </>
  ),
  bell: (
    <>
      <path d="M18 9a6 6 0 0 0-12 0c0 7-3 7-3 7h18s-3 0-3-7" />
      <path d="M10 20h4" />
    </>
  ),
  arrow: <path d="M5 12h14M14 7l5 5-5 5" />,
  plus: <path d="M12 5v14M5 12h14" />,
  close: <path d="m6 6 12 12M18 6 6 18" />,
  chevron: <path d="m9 18 6-6-6-6" />,
  message: <path d="M20 15a3 3 0 0 1-3 3H8l-5 3V7a3 3 0 0 1 3-3h11a3 3 0 0 1 3 3v8Z" />,
  calendar: (
    <>
      <rect x="3" y="5" width="18" height="16" rx="3" />
      <path d="M8 3v4M16 3v4M3 10h18" />
    </>
  ),
  target: (
    <>
      <circle cx="12" cy="12" r="9" />
      <circle cx="12" cy="12" r="4" />
    </>
  ),
};

function Icon({ name, size = 20 }: { name: IconName; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name]}
    </svg>
  );
}

function getInitials(name: string): string {
  const parts = name.trim().split(/\s+/);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

function getTone(name: string): "dark" | "lilac" | "petal" | "slate" {
  const tones: Array<"dark" | "lilac" | "petal" | "slate"> = ["dark", "lilac", "petal", "slate"];
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash);
  const index = Math.abs(hash) % tones.length;
  return tones[index];
}

function Avatar({
  name,
  initials,
  tone,
  size = "md",
}: {
  name?: string;
  initials?: string;
  tone?: "dark" | "lilac" | "petal" | "slate";
  size?: "sm" | "md" | "lg";
}) {
  const finalInitials = initials || (name ? getInitials(name) : "??");
  const finalTone = tone || (name ? getTone(name) : "dark");
  return (
    <span className={`avatar avatar-${size} avatar-${finalTone}`} title={name}>
      {finalInitials}
    </span>
  );
}

function Button({
  children,
  variant = "primary",
  icon,
  onClick,
  type = "button",
  disabled = false,
}: {
  children: ReactNode;
  variant?: "primary" | "soft" | "ghost" | "outline";
  icon?: IconName;
  onClick?: () => void;
  type?: "button" | "submit";
  disabled?: boolean;
}) {
  return (
    <button
      type={type}
      className={`button button-${variant}`}
      onClick={onClick}
      disabled={disabled}
      style={disabled ? { opacity: 0.6, cursor: "not-allowed" } : undefined}
    >
      {children}
      {icon && <Icon name={icon} size={17} />}
    </button>
  );
}

/**
 * Progressive disclosure helpers for concise display across dashboard tabs
 */
function getOneSentenceSummary(text?: string | null, maxChars = 120): string {
  if (!text) return "";
  const cleaned = text.replace(/[*_`>#]/g, "").replace(/\s+/g, " ").trim();
  const match = cleaned.match(/^(.*?)([.!?](?:\s|$)|$)/);
  const firstSentence = (match ? match[1] : cleaned).trim().replace(/[.,:;!?-]+$/, "");
  if (!firstSentence) return "";
  const full = `${firstSentence}.`;
  if (full.length <= maxChars) return full;

  for (const delim of ["; ", " — ", " - ", ", but ", ", while ", ", which ", ", "]) {
    if (firstSentence.includes(delim)) {
      const clause = firstSentence.split(delim)[0].trim().replace(/[.,:;!?-]+$/, "");
      const candidate = `${clause}.`;
      if (candidate.length >= 15 && candidate.length <= maxChars) {
        return candidate;
      }
    }
  }

  const words = firstSentence.split(" ");
  let result = "";
  for (const w of words) {
    if ((result ? result + " " + w : w).length + 1 <= maxChars) {
      result = result ? `${result} ${w}` : w;
    } else {
      break;
    }
  }
  return result ? `${result}.` : `${words[0]}.`;
}

function getCleanShortTitle(title?: string | null, maxChars = 50): string {
  if (!title) return "";
  const cleaned = title.replace(/[*_`]/g, "").trim();
  if (cleaned.length <= maxChars) return cleaned;
  const words = cleaned.split(" ");
  let result = "";
  for (const w of words) {
    if ((result ? result + " " + w : w).length + 1 <= maxChars) {
      result = result ? `${result} ${w}` : w;
    } else {
      break;
    }
  }
  return result ? result : cleaned.slice(0, maxChars);
}

function getShortRecommendation(text?: string | null, maxSentences = 2): string {
  if (!text) return "";
  const cleaned = text.replace(/[*_`>#]/g, "").replace(/\s+/g, " ").trim();
  const sentences = cleaned.split(/(?<=[.!?])\s+/).filter(Boolean);
  if (sentences.length === 0) return cleaned;
  const slice = sentences.slice(0, maxSentences);
  let res = slice.join(" ").trim();
  if (!/[.!?]$/.test(res)) res += ".";
  return res;
}

const severityRank: Record<ConflictSeverity, number> = {
  HIGH: 0,
  MEDIUM: 1,
  LOW: 2,
};

function getConflictSeverity(
  item: { conflict_id?: string; conflict_title?: string; title?: string; severity?: string; reasoning?: string },
  alignmentScore?: number,
  index = 0
): ConflictSeverity {
  if (item.severity && ["HIGH", "MEDIUM", "LOW"].includes(String(item.severity).toUpperCase())) {
    return String(item.severity).toUpperCase() as ConflictSeverity;
  }
  const text = `${item.conflict_title || item.title || ""} ${item.reasoning || ""}`.toLowerCase();
  if (
    index === 0 ||
    (alignmentScore !== undefined && alignmentScore < 45) ||
    text.includes("deadline") ||
    text.includes("date") ||
    text.includes("goal") ||
    text.includes("critical") ||
    text.includes("blocker")
  ) {
    return "HIGH";
  }
  if (text.includes("gap") || text.includes("unclear") || text.includes("missing") || index >= 2) {
    return "LOW";
  }
  return "MEDIUM";
}

function SeverityBadge({
  severity,
  compact = false,
}: {
  severity: ConflictSeverity;
  compact?: boolean;
}) {
  const sev = (severity || "MEDIUM").toUpperCase() as ConflictSeverity;
  const label = sev === "HIGH" ? "High" : sev === "LOW" ? "Low" : "Medium";
  return (
    <span className={`severity-badge severity-${sev.toLowerCase()}`}>
      <i className="severity-badge-dot" />
      {compact ? label : `${label} Severity`}
    </span>
  );
}

const navItems: { name: Page; icon: IconName }[] = [
  { name: "Overview", icon: "grid" },
  { name: "Check-In", icon: "check" },
  { name: "Alignment", icon: "network" },
  { name: "Decisions", icon: "spark" },
  { name: "Team Memory", icon: "clock" },
];

function Sidebar({
  page,
  setPage,
  onCreateProject,
  onManageTeam,
  activeUser,
  decisionsCount,
}: {
  page: Page;
  setPage: (page: Page) => void;
  onCreateProject: () => void;
  onManageTeam: () => void;
  activeUser: string;
  decisionsCount: number;
}) {
  return (
    <aside className="sidebar">
      <button className="brand" onClick={() => setPage("Overview")} aria-label="TeamAlign home">
        <span className="brand-mark">
          <span />
          <span />
          <span />
        </span>
        <span>TeamAlign</span>
      </button>
      <nav className="nav-list">
        {navItems.map((item) => (
          <button
            key={item.name}
            className={`nav-item ${page === item.name ? "active" : ""}`}
            onClick={() => setPage(item.name)}
          >
            <Icon name={item.icon} />
            <span>{item.name}</span>
            {item.name === "Decisions" && decisionsCount > 0 && <b>{decisionsCount}</b>}
          </button>
        ))}
      </nav>
      <div className="sidebar-bottom">
        <button className="nav-item" onClick={onCreateProject}>
          <Icon name="plus" />
          <span>New project</span>
        </button>
        <button className="nav-item" onClick={onManageTeam}>
          <Icon name="settings" />
          <span>Manage team</span>
        </button>
        <div className="user-card">
          <Avatar name={activeUser} size="sm" />
          <span>
            <strong>{activeUser}</strong>
            <small>Active Teammate</small>
          </span>
        </div>
      </div>
    </aside>
  );
}

function Header({
  project,
  projects,
  onSelectProject,
  onCreateProject,
  onManageTeam,
  menuOpen,
  setMenuOpen,
  executionMode,
  isLive,
}: {
  project: Project | null;
  projects: Project[];
  onSelectProject: (id: string) => void;
  onCreateProject: () => void;
  onManageTeam: () => void;
  menuOpen: boolean;
  setMenuOpen: (v: boolean) => void;
  executionMode: string;
  isLive: boolean;
}) {
  const [switcherOpen, setSwitcherOpen] = useState(false);
  const memberCount = project?.members?.length ?? 0;

  return (
    <header className="topbar">
      <button
        className="mobile-menu"
        onClick={() => setMenuOpen(!menuOpen)}
        aria-label="Open navigation"
      >
        <span />
        <span />
        <span />
      </button>
      <div className="project-switcher-wrap">
        <button
          className="project-switcher"
          onClick={() => setSwitcherOpen(!switcherOpen)}
          aria-expanded={switcherOpen}
        >
          <span className="project-icon">
            {project?.title ? project.title.charAt(0).toUpperCase() : "P"}
          </span>
          <span>
            <small>Current project</small>
            <strong>{project?.title || "Select a project"}</strong>
          </span>
          <Icon name="chevron" size={15} />
        </button>
        {switcherOpen && (
          <div className="workspace-menu">
            <span className="eyebrow">Workspaces</span>
            {projects.map((item) => (
              <button
                className={item.id === project?.id ? "active" : ""}
                key={item.id}
                onClick={() => {
                  onSelectProject(item.id);
                  setSwitcherOpen(false);
                }}
              >
                <span>{item.title.charAt(0).toUpperCase()}</span>
                <div>
                  <strong>{item.title}</strong>
                  <small>{item.members?.length || 0} members</small>
                </div>
                {item.id === project?.id && <Icon name="check" size={16} />}
              </button>
            ))}
            <div className="workspace-menu-actions">
              <button
                onClick={() => {
                  onCreateProject();
                  setSwitcherOpen(false);
                }}
              >
                <Icon name="plus" size={16} /> Create project
              </button>
              <button
                onClick={() => {
                  onManageTeam();
                  setSwitcherOpen(false);
                }}
              >
                <Icon name="settings" size={16} /> Manage members
              </button>
            </div>
            <div className="mode-row">
              <span>
                <i style={{ background: isLive ? (apiClient.isMock ? "#eab308" : "#10b981") : "#ef4444" }} />{" "}
                {isLive ? (apiClient.isMock ? "Mock API Connected" : "Live FastAPI Connected") : "API Offline"}
              </span>
              <small>{apiClient.isMock ? "Beeceptor Mock" : executionMode}</small>
            </div>
          </div>
        )}
      </div>
      <div className="topbar-actions">
        <span
          className="mode-indicator"
          style={{
            fontSize: "11px",
            fontWeight: 600,
            padding: "3px 8px",
            borderRadius: "6px",
            background: apiClient.isMock ? "rgba(234, 179, 8, 0.15)" : "rgba(16, 185, 129, 0.15)",
            color: apiClient.isMock ? "#facc15" : "#34d399",
            border: apiClient.isMock ? "1px solid rgba(234, 179, 8, 0.3)" : "1px solid rgba(16, 185, 129, 0.3)",
            display: "inline-flex",
            alignItems: "center",
            gap: "5px",
          }}
        >
          <span
            style={{
              width: 7,
              height: 7,
              borderRadius: "50%",
              background: isLive ? (apiClient.isMock ? "#eab308" : "#10b981") : "#ef4444",
            }}
          />
          {apiClient.isMock ? "MOCK MODE (Beeceptor)" : "LIVE MODE (FastAPI)"}
        </span>
        <span className="data-source" title={`Mode: ${executionMode}`}>
          <Icon name="spark" size={13} /> {executionMode}
        </span>
        <span className="live-pill">
          <i /> {memberCount} members
        </span>
        <div className="avatar-stack">
          {project?.members?.slice(0, 3).map((member) => (
            <Avatar key={member.id} name={member.name} size="sm" />
          ))}
        </div>
      </div>
    </header>
  );
}

function ProjectSetupModal({
  mode,
  project,
  onClose,
  onCreate,
  onAddMember,
}: {
  mode: "create" | "members";
  project: Project | null;
  onClose: () => void;
  onCreate: (title: string, description: string, initialMembers: Array<{ name: string; role: string; email: string }>) => Promise<void>;
  onAddMember: (name: string, role: string, email: string) => Promise<void>;
}) {
  const [step, setStep] = useState(mode === "create" ? 0 : 1);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [pendingMembers, setPendingMembers] = useState<Array<{ name: string; role: string; email: string }>>([
    { name: "Alex Morgan", role: "Frontend", email: "alex@team.co" },
  ]);
  const [memberName, setMemberName] = useState("");
  const [memberEmail, setMemberEmail] = useState("");
  const [memberRole, setMemberRole] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const addPending = () => {
    if (!memberName.trim()) return;
    setPendingMembers((cur) => [
      ...cur,
      {
        name: memberName.trim(),
        email: memberEmail.trim() || `${memberName.toLowerCase().replace(/\s+/g, ".")}@team.co`,
        role: memberRole.trim() || "Teammate",
      },
    ]);
    setMemberName("");
    setMemberEmail("");
    setMemberRole("");
  };

  const handleCreateSubmit = async () => {
    if (!title.trim()) return;
    setLoading(true);
    setError(null);
    try {
      await onCreate(title.trim(), description.trim(), pendingMembers);
      setStep(2);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to create project");
    } finally {
      setLoading(false);
    }
  };

  const handleAddMemberDirect = async () => {
    if (!memberName.trim()) return;
    setLoading(true);
    setError(null);
    try {
      await onAddMember(
        memberName.trim(),
        memberRole.trim() || "Teammate",
        memberEmail.trim() || `${memberName.toLowerCase().replace(/\s+/g, ".")}@team.co`,
      );
      setMemberName("");
      setMemberEmail("");
      setMemberRole("");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to add member");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className="modal-backdrop"
      role="presentation"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <section className="setup-modal" role="dialog" aria-modal="true" aria-labelledby="setup-title">
        <button className="panel-close" onClick={onClose} aria-label="Close">
          <Icon name="close" size={19} />
        </button>
        <div className="setup-progress">
          {["Project", "Team", "Ready"].map((label, index) => (
            <span className={index <= step ? "active" : ""} key={label}>
              <i>{index + 1}</i>
              {label}
            </span>
          ))}
        </div>

        {error && (
          <div style={{ padding: "10px 14px", background: "#fee2e2", color: "#b91c1c", borderRadius: 8, marginBottom: 16, fontSize: 12 }}>
            {error}
          </div>
        )}

        {step === 0 && (
          <div className="setup-content">
            <span className="eyebrow">Create project</span>
            <h2 id="setup-title">Set up a shared workspace.</h2>
            <p>Give your team a focused place for check-ins, alignment, and decisions.</p>
            <label>
              Project title
              <input
                autoFocus
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="e.g. Q4 Platform Launch"
              />
            </label>
            <label>
              What is the team working toward?
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Describe the shared outcome…"
              />
            </label>
            <div className="setup-actions">
              <Button variant="ghost" onClick={onClose}>
                Cancel
              </Button>
              <Button icon="arrow" onClick={() => title.trim() && setStep(1)}>
                Continue
              </Button>
            </div>
          </div>
        )}

        {step === 1 && (
          <div className="setup-content">
            <span className="eyebrow">
              {mode === "create" ? "Invite teammates" : `${project?.title} members`}
            </span>
            <h2 id="setup-title">
              {mode === "create" ? "Bring the right voices in." : "Manage your team roster."}
            </h2>
            <p>Team members independently share their expectations and responsibilities.</p>

            <div className="member-list">
              {mode === "create"
                ? pendingMembers.map((m, idx) => (
                    <div key={idx}>
                      <Avatar name={m.name} size="sm" />
                      <span>
                        <strong>{m.name}</strong>
                        <small>
                          {m.email} · {m.role}
                        </small>
                      </span>
                      <button
                        onClick={() => setPendingMembers((cur) => cur.filter((_, i) => i !== idx))}
                        aria-label={`Remove ${m.name}`}
                      >
                        <Icon name="close" size={15} />
                      </button>
                    </div>
                  ))
                : project?.members?.map((m) => (
                    <div key={m.id}>
                      <Avatar name={m.name} size="sm" />
                      <span>
                        <strong>{m.name}</strong>
                        <small>
                          {m.email || "No email"} · {m.role || "Member"}
                        </small>
                      </span>
                    </div>
                  ))}
            </div>

            <div className="add-member-form">
              <input
                value={memberName}
                onChange={(e) => setMemberName(e.target.value)}
                placeholder="Full name (e.g. Sam Rivera)"
              />
              <input
                value={memberEmail}
                onChange={(e) => setMemberEmail(e.target.value)}
                placeholder="Email (optional)"
                type="email"
              />
              <input
                value={memberRole}
                onChange={(e) => setMemberRole(e.target.value)}
                placeholder="Role (e.g. Backend)"
              />
              <Button
                variant="soft"
                onClick={mode === "create" ? addPending : handleAddMemberDirect}
                disabled={loading}
              >
                <Icon name="plus" size={16} /> Add
              </Button>
            </div>

            <div className="setup-actions">
              {mode === "create" && (
                <Button variant="ghost" onClick={() => setStep(0)}>
                  Back
                </Button>
              )}
              <Button
                icon="arrow"
                onClick={mode === "create" ? handleCreateSubmit : onClose}
                disabled={loading}
              >
                {loading ? "Saving…" : mode === "create" ? "Create project" : "Done"}
              </Button>
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="setup-content setup-ready">
            <span className="completion-mark">
              <Icon name="check" size={28} />
            </span>
            <span className="eyebrow">Workspace ready</span>
            <h2 id="setup-title">{title} is saved to the backend!</h2>
            <p>Start by sharing your perspective, then invite teammates to submit theirs.</p>
            <Button icon="arrow" onClick={onClose}>
              Open workspace
            </Button>
          </div>
        )}
      </section>
    </div>
  );
}

function PageIntro({
  eyebrow,
  title,
  text,
  action,
}: {
  eyebrow: string;
  title: string;
  text: string;
  action?: ReactNode;
}) {
  return (
    <div className="page-intro">
      <div>
        <span className="eyebrow">{eyebrow}</span>
        <h1>{title}</h1>
        <p>{text}</p>
      </div>
      {action}
    </div>
  );
}

function Overview({
  project,
  responses,
  report,
  decisions,
  setPage,
  onManageTeam,
  onSeedDemo,
  isSeeding,
}: {
  project: Project | null;
  responses: MemberResponse[];
  report: SynthesisReport | null;
  decisions: ConfirmedDecision[];
  setPage: (p: Page) => void;
  onManageTeam: () => void;
  onSeedDemo: () => void;
  isSeeding: boolean;
}) {
  if (!project) {
    return (
      <div className="page">
        <PageIntro
          eyebrow="Workspace"
          title="No Project Selected"
          text="Create a project to start gathering team perspectives."
        />
      </div>
    );
  }

  const hasActivity = report !== null;
  const score = report ? Math.round(report.alignment_score) : null;
  const submittedMemberNames = new Set(responses.map((r) => r.member_name.toLowerCase()));
  const conflictsCount = report?.proposed_resolutions?.length ?? 0;
  const openQuestionsCount = report?.proposed_resolutions?.reduce((acc, p) => acc + p.unresolved_questions_for_team.length, 0) ?? 0;

  const decidedResolutionIds = useMemo(
    () => new Set(decisions.map((d) => d.resolution_id)),
    [decisions]
  );

  const unresolvedConflicts = useMemo(() => {
    if (!report?.proposed_resolutions) return [];
    return report.proposed_resolutions
      .filter((r) => !decidedResolutionIds.has(r.resolution_id))
      .sort((a, b) => {
        const sevA = getConflictSeverity(a, report?.alignment_score);
        const sevB = getConflictSeverity(b, report?.alignment_score);
        return severityRank[sevA] - severityRank[sevB];
      });
  }, [report, decidedResolutionIds]);

  const resolvedConflicts = useMemo(() => {
    if (!report?.proposed_resolutions) return [];
    return report.proposed_resolutions.filter((r) =>
      decidedResolutionIds.has(r.resolution_id)
    );
  }, [report, decidedResolutionIds]);

  const highestPriorityConflict = unresolvedConflicts[0] || null;
  const highestPrioritySeverity = highestPriorityConflict
    ? getConflictSeverity(highestPriorityConflict, report?.alignment_score)
    : null;

  const handleReviewResolution = (resolutionId?: string) => {
    setPage("Decisions");
    if (resolutionId) {
      setTimeout(() => {
        const el = document.getElementById(`proposal-${resolutionId}`);
        if (el) {
          el.scrollIntoView({ behavior: "smooth", block: "center" });
          el.style.transition = "outline 0.3s ease, box-shadow 0.3s ease";
          el.style.outline = "2px solid var(--deep-lilac)";
          setTimeout(() => {
            el.style.outline = "none";
          }, 2200);
        }
      }, 120);
    }
  };

  return (
    <div className="page">
      <PageIntro
        eyebrow={`${project.title} workspace`}
        title={`Welcome to ${project.title}.`}
        text={
          hasActivity
            ? `Here’s where ${project.title} stands today based on multi-agent analysis.`
            : `${project.title} is ready. Collect independent perspectives from teammates to detect alignment gaps.`
        }
        action={
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <Button icon="arrow" onClick={() => setPage("Check-In")}>
              {responses.length > 0 ? "Submit check-in" : "Begin first check-in"}
            </Button>
            <Button variant="soft" icon="spark" onClick={onSeedDemo} disabled={isSeeding}>
              {isSeeding ? "Seeding…" : "Seed Demo Scenario"}
            </Button>
          </div>
        }
      />

      {/* What should we do next? Card */}
      {highestPriorityConflict ? (
        <section
          className={`next-action-card severity-${highestPrioritySeverity?.toLowerCase() || "high"}`}
        >
          <div className="next-action-main">
            <div className="next-action-eyebrow">
              <span className="next-action-label">
                <Icon name="spark" size={14} />
                What should we do next?
              </span>
              {highestPrioritySeverity && (
                <SeverityBadge severity={highestPrioritySeverity} />
              )}
            </div>
            <h3 className="next-action-title">
              {getCleanShortTitle(highestPriorityConflict.conflict_title, 55)}
            </h3>
            <p className="next-action-desc">
              {getOneSentenceSummary(
                highestPriorityConflict.recommended_solution,
                140
              )}
            </p>
            {highestPriorityConflict.impacted_members &&
              highestPriorityConflict.impacted_members.length > 0 && (
                <div className="next-action-meta">
                  <div className="next-action-meta-faces">
                    {highestPriorityConflict.impacted_members.map((name) => (
                      <Avatar key={name} name={name} size="sm" />
                    ))}
                  </div>
                  <span className="next-action-meta-text">
                    Requires agreement from{" "}
                    {highestPriorityConflict.impacted_members.join(", ")}
                  </span>
                </div>
              )}
          </div>
          <div className="next-action-cta">
            <Button
              icon="arrow"
              onClick={() => handleReviewResolution(highestPriorityConflict.resolution_id)}
            >
              Review resolution
            </Button>
          </div>
        </section>
      ) : (
        <section className="next-action-card all-caught-up">
          <div className="next-action-main">
            <div className="next-action-eyebrow">
              <span className="next-action-label">
                <Icon name="check" size={14} />
                What should we do next?
              </span>
            </div>
            <h3 className="next-action-title">Your team is all caught up!</h3>
            <p className="next-action-desc">
              {decisions.length > 0
                ? `All detected alignment tensions have confirmed resolutions (${decisions.length} confirmed decision${decisions.length === 1 ? "" : "s"}). Great job maintaining team alignment!`
                : hasActivity && conflictsCount === 0
                ? "No conflicts detected among team check-ins. Your team is in full alignment!"
                : "No unresolved conflicts detected. Gather perspectives from teammates to discover alignment insights."}
            </p>
          </div>
          <div className="next-action-cta">
            <Button
              variant="soft"
              icon="arrow"
              onClick={() => setPage(decisions.length > 0 ? "Team Memory" : hasActivity ? "Alignment" : "Check-In")}
            >
              {decisions.length > 0 ? "View Team Memory" : hasActivity ? "Review alignment" : "Begin check-in"}
            </Button>
          </div>
        </section>
      )}

      <div className="overview-grid">
        <section className="card score-card">
          <div className="card-heading">
            <span>Team alignment</span>
            <span className="trend">
              {hasActivity ? `${conflictsCount} conflicts detected` : "Not analyzed"}
            </span>
          </div>
          <div className="score-row">
            <div className="score-ring">
              <strong>{score !== null ? `${score}%` : "—"}</strong>
              <small>{hasActivity ? "aligned" : "no analysis"}</small>
            </div>
            <div className="score-copy">
              <strong>{hasActivity ? "Multi-Agent Analysis Ready" : "Awaiting check-ins"}</strong>
              <p>
                {hasActivity
                  ? getOneSentenceSummary(report.executive_summary, 120)
                  : "Submit check-ins from at least two teammates, then click Run Analysis."}
              </p>
              <button onClick={() => setPage(hasActivity ? "Alignment" : "Check-In")}>
                {hasActivity ? "Review alignment" : "Start collecting responses"}{" "}
                <Icon name="arrow" size={15} />
              </button>
            </div>
          </div>
        </section>
        <section className="card members-card">
          <div className="card-heading">
            <span>Check-in participation</span>
            <small>
              {responses.length} response{responses.length === 1 ? "" : "s"} submitted
            </small>
          </div>
          {project.members?.map((member) => {
            const hasSubmitted = submittedMemberNames.has(member.name.toLowerCase());
            return (
              <div className="member-row" key={member.id}>
                <Avatar name={member.name} size="sm" />
                <span>
                  <strong>{member.name}</strong>
                  <small>{member.role || "Member"}</small>
                </span>
                <div className="mini-bar">
                  <i style={{ width: hasSubmitted ? "100%" : "8%" }} />
                </div>
                <b>{hasSubmitted ? "Done" : "Open"}</b>
              </div>
            );
          })}
          {(!project.members || project.members.length === 0) && (
            <div className="compact-empty">
              <p>No members added yet.</p>
              <button onClick={onManageTeam}>Add teammates</button>
            </div>
          )}
        </section>
      </div>

      <div className="stats-grid">
        <div className="stat-card">
          <span className="stat-icon">
            <Icon name="check" />
          </span>
          <strong>{report?.key_findings?.length ?? 0}</strong>
          <small>Key Findings</small>
        </div>
        <div className="stat-card">
          <span className="stat-icon lilac">
            <Icon name="network" />
          </span>
          <strong>{conflictsCount}</strong>
          <small>Detected Conflicts</small>
        </div>
        <div className="stat-card">
          <span className="stat-icon slate">
            <Icon name="message" />
          </span>
          <strong>{openQuestionsCount}</strong>
          <small>Open Questions</small>
        </div>
        <div className="stat-card">
          <span className="stat-icon dark">
            <Icon name="spark" />
          </span>
          <strong>{decisions.length}</strong>
          <small>Decisions Made</small>
        </div>
      </div>

      {hasActivity ? (
        <div className="bottom-grid">
          <section className="card issues-card">
            <div className="card-heading">
              <span>Issues Needing Attention</span>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                {unresolvedConflicts.length > 0 && (
                  <span className="unresolved-badge">
                    {unresolvedConflicts.length} open
                  </span>
                )}
                <button onClick={() => setPage("Alignment")}>View all</button>
              </div>
            </div>
            {unresolvedConflicts.length > 0 ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {unresolvedConflicts.slice(0, 3).map((res, idx) => {
                  const sev = getConflictSeverity(res, report.alignment_score, idx);
                  return (
                    <div
                      className="attention-card"
                      key={res.resolution_id || idx}
                      onClick={() => setPage("Alignment")}
                      style={{ cursor: "pointer" }}
                    >
                      <span
                        className="attention-line"
                        style={{
                          background:
                            sev === "HIGH"
                              ? "#e11d48"
                              : sev === "MEDIUM"
                              ? "#d97706"
                              : "var(--deep-lilac)",
                        }}
                      />
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 2 }}>
                          <SeverityBadge severity={sev} compact />
                          <small style={{ margin: 0 }}>
                            Requires consensus · Issue #{idx + 1}
                          </small>
                        </div>
                        <strong>{getCleanShortTitle(res.conflict_title, 48)}</strong>
                        <div className="statement-faces" style={{ marginTop: 4 }}>
                          {res.impacted_members.map((name) => (
                            <Avatar key={name} name={name} size="sm" />
                          ))}
                          <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                            {getOneSentenceSummary(res.recommended_solution, 110)}
                          </span>
                        </div>
                      </div>
                      <Icon name="chevron" />
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="empty-attention">
                <span className="empty-check-icon">
                  <Icon name="check" size={16} />
                </span>
                <p>No open issues! All detected conflicts have confirmed resolutions.</p>
              </div>
            )}

            {/* Resolved section inside Issues Needing Attention */}
            {resolvedConflicts.length > 0 && (
              <div className="resolved-conflicts-section">
                <div className="resolved-conflicts-heading">
                  <span>Resolved Issues ({resolvedConflicts.length})</span>
                  <button onClick={() => setPage("Team Memory")}>
                    View in Team Memory <Icon name="arrow" size={11} />
                  </button>
                </div>
                <div className="resolved-pills-list">
                  {resolvedConflicts.slice(0, 3).map((res) => (
                    <div
                      key={res.resolution_id}
                      className="resolved-pill"
                      onClick={() => setPage("Team Memory")}
                      title="View confirmed resolution in Team Memory"
                    >
                      <span className="resolved-check-dot">
                        <Icon name="check" size={10} />
                      </span>
                      <span className="resolved-title">
                        {getCleanShortTitle(res.conflict_title, 42)}
                      </span>
                      <small>Resolved</small>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </section>
          <section className="card">
            <div className="card-heading">
              <span>Recent decisions</span>
              <button onClick={() => setPage("Team Memory")}>View all</button>
            </div>
            {decisions.length > 0 ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                {decisions.slice(0, 4).map((d) => (
                  <div
                    className="decision-row"
                    key={d.id}
                    onClick={() => setPage("Team Memory")}
                    style={{ cursor: "pointer" }}
                    title="Click to view full decision in Team Memory"
                  >
                    <span>
                      <Icon name="check" size={14} />
                    </span>
                    <div>
                      <strong className="decision-text-clamp" title={d.decision_text}>
                        {getOneSentenceSummary(d.decision_text, 110)}
                      </strong>
                      <div className="decision-meta-row">
                        <small>
                          {d.status} by {d.decided_by} · {new Date(d.decided_at).toLocaleDateString()}
                        </small>
                        <button
                          type="button"
                          className="decision-view-link"
                          onClick={(e) => {
                            e.stopPropagation();
                            setPage("Team Memory");
                          }}
                        >
                          View in Team Memory <Icon name="arrow" size={11} />
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p style={{ fontSize: 12, color: "var(--slate)", marginTop: 10 }}>
                No decisions finalized yet. Review proposals on the Decisions page.
              </p>
            )}
          </section>
        </div>
      ) : (
        <div className="onboarding-callout">
          <div>
            <span className="eyebrow">Recommended next step</span>
            <h2>Collect independent perspectives</h2>
            <p>
              Have team members complete the 5-step check-in (or use the &quot;Seed Demo Scenario&quot; button above) to run Gemini multi-agent analysis.
            </p>
          </div>
          <Button icon="arrow" onClick={() => setPage("Check-In")}>
            Start check-in
          </Button>
        </div>
      )}
    </div>
  );
}

const checkInSteps = ["Goals", "Priorities", "Timing", "Ownership", "Concerns"];
const checkInPrompts = [
  ["What outcome are you working toward?", "Describe the primary outcome or project goal you are aiming for…"],
  ["What matters most right now?", "List top priorities or critical dependencies that must be handled first…"],
  ["What timeline are you working against?", "Specify expected milestone deadlines or launch dates…"],
  ["What are you responsible for?", "Clarify what tasks you own and who you expect to own other deliverables…"],
  ["What could block the team?", "Share risks, unbudgeted testing buffers, or critical bottlenecks…"],
];

function CheckIn({
  project,
  responses,
  onComplete,
  onSubmitResponse,
}: {
  project: Project | null;
  responses: MemberResponse[];
  onComplete: () => void;
  onSubmitResponse: (memberName: string, rawText: string) => Promise<void>;
}) {
  const [selectedMemberName, setSelectedMemberName] = useState<string>(() => {
    return project?.members?.[0]?.name || "Alex Morgan";
  });
  const [step, setStep] = useState(0);
  const [answers, setAnswers] = useState<string[]>(["", "", "", "", ""]);
  const [complete, setComplete] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (project?.members?.length && !project.members.some((m) => m.name === selectedMemberName)) {
      setSelectedMemberName(project.members[0].name);
    }
  }, [project, selectedMemberName]);

  const loadPreset = (persona: "alex" | "sam" | "taylor") => {
    if (persona === "alex") {
      setSelectedMemberName("Alex Morgan");
      setAnswers([
        "Complete and polish the responsive frontend experience for our launch.",
        "Ensure layout fidelity, mobile responsiveness, and clean component interactions.",
        "The project deadline is Saturday and I believe Taylor owns deployment.",
        "I own frontend architecture and styling; Taylor owns deployment.",
        "Launching with unfinished UI polish or without deployment owner coordination.",
      ]);
    } else if (persona === "sam") {
      setSelectedMemberName("Sam Rivera");
      setAnswers([
        "Deliver complete backend services, database durability, and API endpoints.",
        "Ensure all data models, business logic, and security invariants are locked.",
        "The project deadline is Sunday and we need full feature completion before launch.",
        "I own backend routes, SQLite/Supabase storage, and core application logic.",
        "Rushing a launch before all features and services are properly tested.",
      ]);
    } else {
      setSelectedMemberName("Taylor Kim");
      setAnswers([
        "Ensure platform reliability, end-to-end quality assurance, and zero regressions.",
        "Execute automated test suites and verify deployment infrastructure.",
        "I believe Alex owns deployment, and we must complete thorough testing before launching anything.",
        "I own QA regression testing; Alex owns deployment configuration.",
        "Launching without a dedicated 24-hour testing window creates severe risk of outage.",
      ]);
    }
  };

  const handleNextOrSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (step < 4) {
      setStep(step + 1);
      return;
    }

    // Step 4: Submit to backend
    setSubmitting(true);
    setError(null);

    const compiledRawText = [
      `Goals: ${answers[0]}`,
      `Priorities: ${answers[1]}`,
      `Timing: ${answers[2]}`,
      `Ownership: ${answers[3]}`,
      `Concerns: ${answers[4]}`,
    ].join("\n\n");

    try {
      await onSubmitResponse(selectedMemberName, compiledRawText);
      setComplete(true);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to submit check-in to backend.");
    } finally {
      setSubmitting(false);
    }
  };

  if (!project) return <div className="page"><p>Please select a project first.</p></div>;

  if (complete) {
    return (
      <div className="page completion">
        <div className="completion-mark">
          <Icon name="check" size={36} />
        </div>
        <span className="eyebrow">Check-in complete</span>
        <h1>Perspective saved to backend.</h1>
        <p>
          {selectedMemberName}&apos;s responses are safely stored in the database. When your teammates finish, run multi-agent analysis to discover alignment and conflicts.
        </p>
        <div className="agent-progress">
          <span>
            <Icon name="spark" />
            Ready for Multi-Agent Analysis
          </span>
          <i>
            <b />
          </i>
        </div>
        <div style={{ display: "flex", gap: 12 }}>
          <Button icon="arrow" onClick={onComplete}>
            Go to Alignment Map
          </Button>
          <Button
            variant="soft"
            onClick={() => {
              setComplete(false);
              setStep(0);
              setAnswers(["", "", "", "", ""]);
            }}
          >
            Submit another teammate
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="page checkin-page">
      <PageIntro
        eyebrow={`${project.title} · Private Check-In`}
        title="Share your perspective."
        text="Submit your independent goals, timeline, and responsibilities. The AI compares responses to uncover hidden disagreements."
        action={
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <span style={{ fontSize: 11, color: "var(--slate)" }}>Quick presets:</span>
            <button
              className="button button-soft"
              style={{ minHeight: 32, padding: "0 10px", fontSize: 11 }}
              onClick={() => loadPreset("alex")}
            >
              Alex (Sat)
            </button>
            <button
              className="button button-soft"
              style={{ minHeight: 32, padding: "0 10px", fontSize: 11 }}
              onClick={() => loadPreset("sam")}
            >
              Sam (Sun)
            </button>
            <button
              className="button button-soft"
              style={{ minHeight: 32, padding: "0 10px", fontSize: 11 }}
              onClick={() => loadPreset("taylor")}
            >
              Taylor (QA)
            </button>
          </div>
        }
      />

      {error && (
        <div style={{ padding: "12px 16px", background: "#fee2e2", color: "#b91c1c", borderRadius: 10, marginBottom: 18, fontSize: 13 }}>
          {error}
        </div>
      )}

      <div style={{ marginBottom: 20, display: "flex", gap: 12, alignItems: "center" }}>
        <label style={{ fontSize: 12, fontWeight: 600, color: "var(--slate)" }}>Submitting as:</label>
        <select
          value={selectedMemberName}
          onChange={(e) => setSelectedMemberName(e.target.value)}
          style={{ padding: "8px 12px", borderRadius: 8, border: "1px solid var(--line)", background: "var(--canvas)", fontSize: 13 }}
        >
          {project.members?.map((m) => (
            <option key={m.id} value={m.name}>
              {m.name} ({m.role || "Member"})
            </option>
          ))}
          {!project.members?.length && <option value="Alex Morgan">Alex Morgan</option>}
        </select>
        <span style={{ fontSize: 11, color: "var(--slate)", marginLeft: "auto" }}>
          {responses.length} responses stored in database
        </span>
      </div>

      <div className="checkin-shell">
        <div className="steps">
          {checkInSteps.map((name, i) => (
            <button
              key={name}
              className={i === step ? "active" : i < step ? "done" : ""}
              onClick={() => i <= step && setStep(i)}
            >
              <span>{i < step ? <Icon name="check" size={14} /> : i + 1}</span>
              <small>{name}</small>
            </button>
          ))}
        </div>

        <form className="checkin-card" onSubmit={handleNextOrSubmit}>
          <div className="form-number">0{step + 1}</div>
          <span className="eyebrow">{checkInSteps[step]}</span>
          <h2>{checkInPrompts[step][0]}</h2>
          <p>Be candid. Your answers are compared with teammates to find hidden misalignments.</p>

          <textarea
            autoFocus
            key={step}
            placeholder={checkInPrompts[step][1]}
            required
            value={answers[step]}
            onChange={(e) => {
              const val = e.target.value;
              setAnswers((cur) => cur.map((item, idx) => (idx === step ? val : item)));
            }}
          />

          <div className="form-footer">
            <span>
              <Icon name="check" size={16} /> Step {step + 1} of 5
            </span>
            <div>
              {step > 0 && (
                <Button variant="ghost" onClick={() => setStep(step - 1)}>
                  Back
                </Button>
              )}
              <Button type="submit" icon="arrow" disabled={submitting}>
                {submitting ? "Submitting…" : step === 4 ? "Submit check-in" : "Continue"}
              </Button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}

function Alignment({
  project,
  analysisResult,
  report,
  responses,
  onRunAnalysis,
  analyzing,
  error,
  onStartCheckIn,
  setPage,
}: {
  project: Project | null;
  analysisResult: AlignmentWorkflowResult | null;
  report: SynthesisReport | null;
  responses: MemberResponse[];
  onRunAnalysis: () => Promise<void>;
  analyzing: boolean;
  error: string | null;
  onStartCheckIn: () => void;
  setPage: (p: Page) => void;
}) {
  const [viewMode, setViewMode] = useState<"conflicts" | "perspectives">("conflicts");
  const [filter, setFilter] = useState<"All" | "Agreements" | "Conflicts">("All");
  const [selectedConflictId, setSelectedConflictId] = useState<string | null>(null);
  const [showDetails, setShowDetails] = useState(false);

  if (!project) return <div className="page"><p>Please select a project first.</p></div>;

  const { conflicts, compatibleDifferences, perspectives, hasAnalysis, score, executionMode } = useMemo(() => {
    if (analysisResult) {
      return {
        conflicts: analysisResult.conflicts_output?.conflicts || [],
        compatibleDifferences: analysisResult.conflicts_output?.compatible_differences || [],
        perspectives: analysisResult.perspectives_output?.perspectives || [],
        hasAnalysis: true,
        score: Math.round(analysisResult.synthesis_output?.alignment_score ?? 0),
        executionMode: analysisResult.execution_mode || "MOCK_DETERMINISTIC",
      };
    }

    if (report) {
      // Derive conflicts from saved synthesis report
      const derivedConflicts: DetectedConflict[] = (report.proposed_resolutions || []).map((res, idx) => {
        const evidence: EvidenceItem[] = [];
        const lowerTitle = (res.conflict_title || "").toLowerCase();
        const keywords = lowerTitle
          .replace(/[^a-z0-9 ]/g, " ")
          .split(/\s+/)
          .filter((w) => w.length > 3 && !["with", "from", "that", "this", "about", "scope", "issue"].includes(w));

        for (const member of res.impacted_members || []) {
          const mLower = member.toLowerCase();
          const memberResps = responses.filter((r) => r.member_name.toLowerCase() === mLower);
          const keywordMatch = memberResps.find((r) => keywords.some((kw) => r.raw_text.toLowerCase().includes(kw)));
          const chosen = keywordMatch || memberResps[0];
          if (chosen) {
            evidence.push({
              member_name: chosen.member_name,
              quote: chosen.raw_text,
              interpretation: `Statement from ${chosen.member_name} regarding ${res.conflict_title}.`,
            });
          }
        }

        if (evidence.length === 0 && responses.length > 0) {
          const matchedResp = responses.find((r) => keywords.some((kw) => r.raw_text.toLowerCase().includes(kw))) || responses[0];
          evidence.push({
            member_name: matchedResp.member_name,
            quote: matchedResp.raw_text,
            interpretation: `Check-in statement from ${matchedResp.member_name}.`,
          });
        }

        let cType: ConflictType = "PRIORITY_MISMATCH";
        if (lowerTitle.includes("deadline") || lowerTitle.includes("date") || lowerTitle.includes("time") || lowerTitle.includes("schedule")) {
          cType = "DEADLINE_CONTRADICTION";
        } else if (lowerTitle.includes("responsibility") || lowerTitle.includes("owner") || lowerTitle.includes("assign") || lowerTitle.includes("integration")) {
          cType = "RESPONSIBILITY_OVERLAP_OR_GAP";
        } else if (lowerTitle.includes("goal") || lowerTitle.includes("scope") || lowerTitle.includes("vision")) {
          cType = "GOAL_INCOMPATIBILITY";
        } else if (lowerTitle.includes("gap") || lowerTitle.includes("missing")) {
          cType = "INFORMATION_GAP";
        } else if (lowerTitle.includes("process") || lowerTitle.includes("design") || lowerTitle.includes("mismatch")) {
          cType = "PROCESS_MISALIGNMENT";
        }

        let severity: ConflictSeverity = "MEDIUM";
        if ((res as any).severity && ["HIGH", "MEDIUM", "LOW"].includes(String((res as any).severity).toUpperCase())) {
          severity = String((res as any).severity).toUpperCase() as ConflictSeverity;
        } else if (idx === 0 || report.alignment_score < 45 || cType === "DEADLINE_CONTRADICTION" || cType === "GOAL_INCOMPATIBILITY") {
          severity = "HIGH";
        } else if (cType === "INFORMATION_GAP" || idx >= 2) {
          severity = "LOW";
        } else {
          severity = "MEDIUM";
        }

        return {
          conflict_id: res.conflict_id || `CONF-${idx + 1}`,
          title: res.conflict_title,
          conflict_type: cType,
          category: "DIRECT_DISAGREEMENT" as ConflictCategory,
          severity,
          severity_reasoning: res.reasoning,
          parties_involved: res.impacted_members || [],
          evidence,
          impact_description: res.recommended_solution,
        };
      });

      const memberMap = new Map<string, string[]>();
      for (const r of responses) {
        const existing = memberMap.get(r.member_name) || [];
        existing.push(r.raw_text);
        memberMap.set(r.member_name, existing);
      }

      const derivedPerspectives: ExtractedPerspective[] = Array.from(memberMap.entries()).map(([name, quotes]) => ({
        member_name: name,
        goals: quotes.slice(0, 1).map((q) => ({ statement: q.slice(0, 80) + (q.length > 80 ? "…" : ""), source_quote: q, clarity: "CLEAR" })),
        priorities: [],
        responsibilities: [],
        deadlines: [],
        ambiguities_or_missing_details: [],
        key_quotes: quotes,
      }));

      return {
        conflicts: derivedConflicts,
        compatibleDifferences: report.key_findings || [],
        perspectives: derivedPerspectives,
        hasAnalysis: true,
        score: Math.round(report.alignment_score),
        executionMode: "SAVED_ANALYSIS",
      };
    }

    return {
      conflicts: [],
      compatibleDifferences: [],
      perspectives: [],
      hasAnalysis: false,
      score: 0,
      executionMode: "MOCK_DETERMINISTIC",
    };
  }, [analysisResult, report, responses, project?.title]);

  const sortedConflicts = useMemo(() => {
    return [...conflicts].sort((a, b) => {
      const rA = severityRank[a.severity] ?? 1;
      const rB = severityRank[b.severity] ?? 1;
      return rA - rB;
    });
  }, [conflicts]);

  const selectedConflict = sortedConflicts.find((c) => c.conflict_id === selectedConflictId) || sortedConflicts[0];

  const visibleConflicts = filter === "Agreements" ? [] : sortedConflicts;
  const visibleAgreements = filter === "Conflicts" ? [] : compatibleDifferences;

  return (
    <div className="page alignment-page">
      <PageIntro
        eyebrow={`${project.title} · Alignment Studio`}
        title="See where your team stands."
        text="Perspective Agent extracts statements, Conflict Agent finds contradictions, and Resolution Agent drafts compromise options."
        action={
          <Button variant="soft" onClick={onRunAnalysis} disabled={analyzing}>
            {analyzing ? <span className="button-spinner" /> : <Icon name="spark" size={16} />}
            {analyzing ? "Running Gemini Multi-Agent…" : "Run Analysis"}
          </Button>
        }
      />

      {error && (
        <div style={{ padding: "12px 16px", background: "#fee2e2", color: "#b91c1c", borderRadius: 10, marginBottom: 18, fontSize: 13 }}>
          {error}
        </div>
      )}

      {analyzing && (
        <div className="analysis-loading">
          <span className="button-spinner" />
          <p>
            <strong>Google ADK multi-agent pipeline is executing</strong>
            <small>Comparing goals, deadlines, and responsibilities across team perspectives…</small>
          </p>
        </div>
      )}

      {!hasAnalysis && !analyzing ? (
        <div className="page-empty">
          <span>
            <Icon name="network" size={24} />
          </span>
          <h2>No analysis run yet</h2>
          <p>
            Collect teammate check-ins (at least 2 responses), then click &quot;Run Analysis&quot; to execute the multi-agent alignment workflow.
          </p>
          <Button icon="arrow" onClick={onStartCheckIn}>
            Submit a check-in
          </Button>
        </div>
      ) : (
        <>
          <div className="filter-row">
            <button
              className={viewMode === "conflicts" && filter === "All" ? "active" : ""}
              onClick={() => {
                setViewMode("conflicts");
                setFilter("All");
              }}
            >
              All Findings <span>{conflicts.length + compatibleDifferences.length}</span>
            </button>
            <button
              className={viewMode === "conflicts" && filter === "Conflicts" ? "active" : ""}
              onClick={() => {
                setViewMode("conflicts");
                setFilter("Conflicts");
              }}
            >
              Conflicts <span>{conflicts.length}</span>
            </button>
            <button
              className={viewMode === "conflicts" && filter === "Agreements" ? "active" : ""}
              onClick={() => {
                setViewMode("conflicts");
                setFilter("Agreements");
              }}
            >
              Agreements <span>{compatibleDifferences.length}</span>
            </button>
            <button
              className={viewMode === "perspectives" ? "active" : ""}
              onClick={() => setViewMode("perspectives")}
            >
              Perspective Map <span>{perspectives.length}</span>
            </button>
            <div className="legend" style={{ marginLeft: "auto", display: "flex", gap: 14 }}>
              <span className="data-source">
                <Icon name="spark" size={12} /> {executionMode}
              </span>
              <span style={{ fontSize: 12, fontWeight: 700, color: "var(--deep-lilac)" }}>
                Score: {score}%
              </span>
            </div>
          </div>

          {viewMode === "perspectives" ? (
            <div className="perspectives-view">
              <div className="agent-banner">
                <div className="agent-banner-header">
                  <div>
                    <Icon name="spark" size={16} />
                    <span>Agent 1 · Perspective Extraction Map</span>
                  </div>
                  <small style={{ color: "var(--slate)" }}>
                    {perspectives.length} teammate perspectives analyzed
                  </small>
                </div>
                <p>
                  {analysisResult?.perspectives_output?.overall_summary ||
                    "Structured viewpoints extracted independently from each team member."}
                </p>
                {analysisResult?.perspectives_output?.identified_gaps &&
                  analysisResult.perspectives_output.identified_gaps.length > 0 && (
                    <div style={{ marginTop: 6 }}>
                      <span style={{ fontSize: 10, fontWeight: 700, color: "var(--deep-lilac)" }}>
                        Identified Information Gaps:
                      </span>
                      <div className="gaps-list">
                        {analysisResult.perspectives_output.identified_gaps.map((gap, idx) => (
                          <span key={idx} className="gap-tag">
                            {gap}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
              </div>

              <div className="perspectives-grid">
                {perspectives.map((p) => {
                  const memberInfo = project.members?.find(
                    (m) => m.name.toLowerCase() === p.member_name.toLowerCase(),
                  );
                  return (
                    <article className="perspective-card" key={p.member_name}>
                      <div className="perspective-card-header">
                        <Avatar name={p.member_name} size="md" />
                        <div>
                          <strong>{p.member_name}</strong>
                          <small>{memberInfo?.role || "Teammate"}</small>
                        </div>
                      </div>

                      {p.goals && p.goals.length > 0 && (
                        <div className="perspective-section">
                          <span className="perspective-section-title">Stated Goals</span>
                          {p.goals.map((g, idx) => (
                            <div className="perspective-item" key={idx}>
                              <strong>{g.statement}</strong>
                              {g.clarity && (
                                <span className={`pill-badge ${g.clarity.toLowerCase()}`}>
                                  {g.clarity}
                                </span>
                              )}
                              {g.source_quote && <small>&ldquo;{g.source_quote}&rdquo;</small>}
                            </div>
                          ))}
                        </div>
                      )}

                      {p.priorities && p.priorities.length > 0 && (
                        <div className="perspective-section">
                          <span className="perspective-section-title">Top Priorities</span>
                          {p.priorities.map((pr, idx) => (
                            <div className="perspective-item" key={idx}>
                              <strong>{pr.priority_item}</strong>
                              {pr.urgency_level && (
                                <span className={`pill-badge ${pr.urgency_level.toLowerCase()}`}>
                                  {pr.urgency_level}
                                </span>
                              )}
                              {pr.source_quote && <small>&ldquo;{pr.source_quote}&rdquo;</small>}
                            </div>
                          ))}
                        </div>
                      )}

                      {p.deadlines && p.deadlines.length > 0 && (
                        <div className="perspective-section">
                          <span className="perspective-section-title">Expected Timeline</span>
                          {p.deadlines.map((dl, idx) => (
                            <div className="perspective-item" key={idx}>
                              <span>
                                {dl.milestone}: <b>{dl.expected_deadline}</b>
                              </span>
                              {dl.is_tentative && (
                                <span className="pill-badge normal">Tentative</span>
                              )}
                              {dl.source_quote && <small>&ldquo;{dl.source_quote}&rdquo;</small>}
                            </div>
                          ))}
                        </div>
                      )}

                      {p.responsibilities && p.responsibilities.length > 0 && (
                        <div className="perspective-section">
                          <span className="perspective-section-title">Responsibilities & Ownership</span>
                          {p.responsibilities.map((resp, idx) => (
                            <div className="perspective-item" key={idx}>
                              <span>
                                {resp.responsibility} &rarr; <b>{resp.assigned_to}</b>
                              </span>
                              {resp.source_quote && <small>&ldquo;{resp.source_quote}&rdquo;</small>}
                            </div>
                          ))}
                        </div>
                      )}

                      {p.key_quotes && p.key_quotes.length > 0 && (
                        <div className="perspective-section">
                          <span className="perspective-section-title">Key Statement</span>
                          <blockquote className="quote-box">&ldquo;{p.key_quotes[0]}&rdquo;</blockquote>
                        </div>
                      )}

                      {p.ambiguities_or_missing_details &&
                        p.ambiguities_or_missing_details.length > 0 && (
                          <div className="perspective-section">
                            <span
                              className="perspective-section-title"
                              style={{ color: "var(--slate)" }}
                            >
                              Missing Details / Ambiguities
                            </span>
                            {p.ambiguities_or_missing_details.map((amb, idx) => (
                              <div
                                key={idx}
                                style={{
                                  fontSize: 10,
                                  color: "var(--slate)",
                                  fontStyle: "italic",
                                }}
                              >
                                &bull; {amb}
                              </div>
                            ))}
                          </div>
                        )}
                    </article>
                  );
                })}
              </div>
            </div>
          ) : (
            <div className="alignment-list-shell">
              <section className="comparison-list">
                <div className="comparison-list-heading">
                  <div>
                    <span className="eyebrow">Multi-agent findings</span>
                    <h2>Detected Issues & Agreements</h2>
                  </div>
                  <small>
                    {visibleConflicts.length + visibleAgreements.length} item(s)
                  </small>
                </div>

                {visibleConflicts.map((c) => {
                  const isSelected = selectedConflict?.conflict_id === c.conflict_id;
                  return (
                    <button
                      key={c.conflict_id}
                      className={`comparison-row ${isSelected ? "active" : ""}`}
                      onClick={() => setSelectedConflictId(c.conflict_id)}
                    >
                      <span className="finding-marker">
                        <Icon name="network" size={17} />
                      </span>
                      <span className="comparison-copy">
                        <div style={{ display: "flex", alignItems: "center", gap: 7, flexWrap: "wrap", marginBottom: 3 }}>
                          <SeverityBadge severity={c.severity} compact />
                          <span className="finding-label conflict">
                            {c.conflict_type.replace(/_/g, " ")}
                          </span>
                        </div>
                        <strong>{getCleanShortTitle(c.title, 48)}</strong>
                        <small>{getOneSentenceSummary(c.impact_description || c.severity_reasoning || c.title, 140)}</small>
                      </span>
                      <span className="comparison-people">
                        {c.parties_involved.map((p) => (
                          <Avatar key={p} name={p} size="sm" />
                        ))}
                      </span>
                      <Icon name="chevron" size={18} />
                    </button>
                  );
                })}

                {visibleAgreements.map((diffText, idx) => (
                  <div key={idx} className="comparison-row">
                    <span className="finding-marker agreement">
                      <Icon name="check" size={17} />
                    </span>
                    <span className="comparison-copy">
                      <span className="finding-label agreement">Shared Alignment</span>
                      <strong>Compatible Perspectives</strong>
                      <small>{getOneSentenceSummary(diffText, 140)}</small>
                    </span>
                  </div>
                ))}
              </section>

              {selectedConflict && (
                <aside className="insight-panel">
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
                    <SeverityBadge severity={selectedConflict.severity} />
                    <span className="section-label" style={{ margin: 0 }}>CONFLICT</span>
                  </div>
                  <h2>{getCleanShortTitle(selectedConflict.title, 48)}</h2>
                  <p style={{ fontSize: 13, color: "var(--ink)", margin: "8px 0", lineHeight: 1.5 }}>
                    {getOneSentenceSummary(selectedConflict.impact_description || selectedConflict.severity_reasoning, 140)}
                  </p>
                  <div className="confidence">
                    <span>
                      <i
                        style={{
                          width: selectedConflict.severity === "HIGH" ? "95%" : selectedConflict.severity === "MEDIUM" ? "70%" : "45%",
                        }}
                      />
                    </span>
                    <small>{selectedConflict.category.replace(/_/g, " ")}</small>
                  </div>

                  <button
                    className="view-details-toggle"
                    type="button"
                    onClick={() => setShowDetails(!showDetails)}
                    style={{
                      background: "var(--blush)",
                      border: "1px solid var(--line)",
                      borderRadius: 8,
                      padding: "6px 12px",
                      color: "var(--deep-lilac)",
                      cursor: "pointer",
                      fontWeight: 600,
                      fontSize: 12,
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 6,
                      margin: "12px 0",
                    }}
                  >
                    <Icon name="spark" size={14} />
                    {showDetails ? "Hide details" : "View details"}
                  </button>

                  {showDetails && (
                    <div>
                      <div className="ai-summary">
                        <span>
                          <Icon name="spark" size={16} /> Conflict Agent Finding
                        </span>
                        <p>{selectedConflict.severity_reasoning}</p>
                      </div>

                      <div style={{ margin: "14px 0", fontSize: 11, color: "var(--slate)" }}>
                        <strong>Impact:</strong> {selectedConflict.impact_description}
                      </div>

                      <div className="quotes">
                        <span className="section-label">Verbatim Evidence Citations</span>
                        {selectedConflict.evidence && selectedConflict.evidence.length > 0 ? (
                          selectedConflict.evidence.map((ev, i) => (
                            <blockquote key={i}>
                              <Avatar name={ev.member_name} size="sm" />
                              <div>
                                <strong>{ev.member_name}</strong>
                                <p>&ldquo;{ev.quote}&rdquo;</p>
                                <small style={{ color: "var(--slate)", fontSize: 9 }}>
                                  {ev.interpretation}
                                </small>
                              </div>
                            </blockquote>
                          ))
                        ) : (
                          <p style={{ fontSize: 11, color: "var(--slate)", fontStyle: "italic", margin: "6px 0" }}>
                            No specific quotes cited for this item.
                          </p>
                        )}
                      </div>
                    </div>
                  )}

                  <Button icon="arrow" onClick={() => setPage("Decisions")}>
                    Explore Resolution Options
                  </Button>
                </aside>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function Decisions({
  project,
  report,
  decisions,
  onRecordDecision,
  recording,
  activeUser,
}: {
  project: Project | null;
  report: SynthesisReport | null;
  decisions: ConfirmedDecision[];
  onRecordDecision: (resolutionId: string, action: "APPROVE" | "REJECT" | "MODIFY", customText?: string) => Promise<void>;
  recording: boolean;
  activeUser: string;
}) {
  const [modifyingResolutionId, setModifyingResolutionId] = useState<string | null>(null);
  const [customText, setCustomText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [expandedReasoning, setExpandedReasoning] = useState<Record<string, boolean>>({});

  if (!project) return <div className="page"><p>Please select a project first.</p></div>;

  const proposals = report?.proposed_resolutions || [];
  const decisionMap = new Map(decisions.map((d) => [d.resolution_id, d]));

  const handleAction = async (resolutionId: string, action: "APPROVE" | "REJECT" | "MODIFY", custom?: string) => {
    setError(null);
    try {
      await onRecordDecision(resolutionId, action, custom);
      setModifyingResolutionId(null);
      setCustomText("");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to record decision.");
    }
  };

  return (
    <div className="page">
      <PageIntro
        eyebrow={`${project.title} · Decision Studio`}
        title="Turn tension into shared commitments."
        text="AI-generated resolution proposals require human confirmation. Only explicitly approved or modified actions become binding commitments."
      />

      {error && (
        <div style={{ padding: "12px 16px", background: "#fee2e2", color: "#b91c1c", borderRadius: 10, marginBottom: 18, fontSize: 13 }}>
          {error}
        </div>
      )}

      <div className="agent-strip">
        <div>
          <span>
            <Icon name="spark" />
          </span>
          <p>
            <strong>Resolution & Synthesis Agent</strong>
            <small>
              {report
                ? `${proposals.length} resolution proposal(s) generated with governance status="PROPOSED"`
                : "Run multi-agent analysis to generate compromise solutions."}
            </small>
          </p>
        </div>
        <span className="status-dot">
          {proposals.length > 0 ? "Ready for human sign-off" : "Awaiting analysis"}
        </span>
      </div>

      {proposals.length === 0 ? (
        <div className="page-empty">
          <span>
            <Icon name="spark" size={24} />
          </span>
          <h2>No resolution proposals yet</h2>
          <p>Run the alignment analysis on teammate check-ins to generate actionable compromise proposals.</p>
        </div>
      ) : (
        <div className="proposal-list">
          {proposals.map((p, i) => {
            const confirmed = decisionMap.get(p.resolution_id);
            const isModifying = modifyingResolutionId === p.resolution_id;
            const isExpanded = !!expandedReasoning[p.resolution_id];

            return (
              <article className="proposal-card" key={p.resolution_id} id={`proposal-${p.resolution_id}`}>
                <div className="proposal-rank">0{i + 1}</div>
                <div className="proposal-main">
                  <div className="proposal-title">
                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                      <SeverityBadge severity={getConflictSeverity(p, report?.alignment_score, i)} compact />
                      <span className="eyebrow" style={{ margin: 0 }}>
                        {p.resolution_id} · Addressing {getCleanShortTitle(p.conflict_title, 48)}
                      </span>
                    </div>
                    <h2>{getShortRecommendation(p.recommended_solution, 2)}</h2>
                  </div>

                  <button
                    type="button"
                    className="why-recommendation-toggle"
                    onClick={() =>
                      setExpandedReasoning((prev) => ({
                        ...prev,
                        [p.resolution_id]: !prev[p.resolution_id],
                      }))
                    }
                    style={{
                      background: "var(--blush)",
                      border: "1px solid var(--line)",
                      borderRadius: 8,
                      padding: "6px 12px",
                      color: "var(--deep-lilac)",
                      fontSize: 12,
                      fontWeight: 600,
                      cursor: "pointer",
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 6,
                      margin: "12px 0 8px",
                    }}
                  >
                    <Icon name="spark" size={14} />
                    {isExpanded ? "Hide recommendation details" : "Why this recommendation?"}
                  </button>

                  {isExpanded && (
                    <div style={{ marginTop: 8 }}>
                      <div className="reasoning">
                        <span>
                          <Icon name="spark" size={16} /> Why this works
                        </span>
                        <p>{p.reasoning}</p>
                      </div>

                      {p.alternative_options.length > 0 && (
                        <div className="tradeoffs" style={{ marginTop: 12 }}>
                          <span style={{ fontWeight: 600, color: "var(--slate)" }}>Alternatives:</span>
                          {p.alternative_options.map((opt) => (
                            <span key={opt.option_id} title={opt.description}>
                              <i>+</i> {opt.title}
                            </span>
                          ))}
                        </div>
                      )}

                      {p.unresolved_questions_for_team.length > 0 && (
                        <div style={{ marginTop: 14, padding: "10px 14px", background: "var(--soft-paper)", borderRadius: 10, border: "1px solid var(--line)" }}>
                          <strong style={{ fontSize: 11, color: "var(--deep-lilac)" }}>Consensus Questions:</strong>
                          <ul style={{ margin: "6px 0 0 16px", fontSize: 11, color: "var(--slate)", lineHeight: 1.5 }}>
                            {p.unresolved_questions_for_team.map((q, idx) => (
                              <li key={idx}>{q}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  )}

                  {isModifying && (
                    <div style={{ marginTop: 16, padding: 14, background: "var(--blush)", borderRadius: 12 }}>
                      <label style={{ fontSize: 11, fontWeight: 700, display: "block", marginBottom: 6 }}>
                        Enter Custom Modified Commitment:
                      </label>
                      <textarea
                        style={{ width: "100%", height: 70, padding: 10, borderRadius: 8, border: "1px solid var(--line)", background: "var(--canvas)", fontSize: 12 }}
                        value={customText}
                        onChange={(e) => setCustomText(e.target.value)}
                        placeholder="e.g. Frontend complete Saturday noon; dedicated QA Saturday afternoon; soft launch Sunday 10am."
                      />
                      <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                        <Button
                          variant="primary"
                          onClick={() => handleAction(p.resolution_id, "MODIFY", customText)}
                          disabled={recording || !customText.trim()}
                        >
                          Save Modified Decision
                        </Button>
                        <Button variant="ghost" onClick={() => setModifyingResolutionId(null)}>
                          Cancel
                        </Button>
                      </div>
                    </div>
                  )}

                  {!confirmed ? (
                    <div className="decision-actions">
                      <Button
                        onClick={() => handleAction(p.resolution_id, "APPROVE", p.recommended_solution)}
                        disabled={recording}
                      >
                        <Icon name="check" size={17} /> Approve ({activeUser})
                      </Button>
                      <Button
                        variant="outline"
                        onClick={() => {
                          setModifyingResolutionId(p.resolution_id);
                          setCustomText(p.recommended_solution);
                        }}
                        disabled={recording}
                      >
                        Modify Terms
                      </Button>
                      <Button
                        variant="ghost"
                        onClick={() => handleAction(p.resolution_id, "REJECT")}
                        disabled={recording}
                      >
                        Reject
                      </Button>
                    </div>
                  ) : (
                    <div className="action-result">
                      <span>
                        <Icon name="check" size={17} />
                      </span>
                      <p>
                        <strong>
                          {confirmed.status}: {confirmed.decision_text}
                        </strong>
                        <small>
                          Signed off by {confirmed.decided_by} at {new Date(confirmed.decided_at).toLocaleString()}
                        </small>
                      </p>
                    </div>
                  )}
                </div>
                <div className="fit-score">
                  <strong>RES</strong>
                  <small>{p.resolution_id}</small>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}

function TeamMemory({
  project,
  decisions,
}: {
  project: Project | null;
  decisions: ConfirmedDecision[];
}) {
  const [query, setQuery] = useState("");
  const [expandedHistory, setExpandedHistory] = useState<Record<string, boolean>>({});

  if (!project) return <div className="page"><p>Please select a project first.</p></div>;

  const filtered = useMemo(() => {
    return decisions.filter((d) =>
      `${d.decision_text} ${d.decided_by} ${d.status}`.toLowerCase().includes(query.toLowerCase()),
    );
  }, [decisions, query]);

  return (
    <div className="page">
      <PageIntro
        eyebrow={`${project.title} · Team Memory`}
        title="Persistent Commitments & History"
        text="A shared, tamper-evident record of all human decisions approved and signed off in this workspace."
      />

      <div className="memory-tools">
        <label>
          <Icon name="target" size={18} />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search team memory…"
          />
        </label>
        <Button variant="soft">
          <Icon name="calendar" size={17} /> {decisions.length} recorded
        </Button>
      </div>

      {filtered.length === 0 ? (
        <div className="page-empty">
          <span>
            <Icon name="clock" size={24} />
          </span>
          <h2>No recorded decisions in memory</h2>
          <p>
            When teammates approve or modify resolutions in Decision Studio, they are permanently stored in SQLite and appear here.
          </p>
        </div>
      ) : (
        <div className="timeline">
          {filtered.map((d, i) => {
            const isExpanded = !!expandedHistory[d.id];
            return (
              <article className="timeline-event" key={d.id}>
                <div className="timeline-marker">
                  <span>{new Date(d.decided_at).toLocaleDateString()}</span>
                  <i>
                    <Icon name={d.status === "APPROVED" ? "check" : "target"} size={16} />
                  </i>
                </div>
                <div className="memory-card">
                  <span className="memory-type">{d.status} COMMITMENT</span>
                  <h2>{getCleanShortTitle(d.decision_text, 60)}</h2>
                  <p>{getOneSentenceSummary(d.decision_text, 120)}</p>

                  <button
                    type="button"
                    className="view-details-toggle"
                    onClick={() =>
                      setExpandedHistory((prev) => ({
                        ...prev,
                        [d.id]: !prev[d.id],
                      }))
                    }
                    style={{
                      background: "var(--blush)",
                      border: "1px solid var(--line)",
                      borderRadius: 8,
                      padding: "5px 10px",
                      color: "var(--deep-lilac)",
                      fontSize: 11,
                      fontWeight: 600,
                      cursor: "pointer",
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 5,
                      margin: "8px 0 10px",
                    }}
                  >
                    <Icon name="clock" size={13} />
                    {isExpanded ? "Hide history & details" : "View history & details"}
                  </button>

                  {isExpanded && (
                    <div style={{ marginTop: 8, marginBottom: 12, padding: "10px 14px", background: "var(--canvas)", borderRadius: 10, border: "1px solid var(--line)" }}>
                      <strong style={{ fontSize: 11, color: "var(--ink)", display: "block", marginBottom: 4 }}>
                        Full Binding Commitment:
                      </strong>
                      <p style={{ fontSize: 12, color: "var(--ink)", lineHeight: 1.5, margin: "0 0 8px" }}>
                        {d.decision_text}
                      </p>
                      <div style={{ fontSize: 10, color: "var(--slate)", display: "flex", flexWrap: "wrap", gap: 12 }}>
                        <span>Resolution ID: <b>{d.resolution_id}</b></span>
                        <span>Decision ID: <b>{d.id}</b></span>
                        <span>Status: <b>{d.status}</b></span>
                        <span>Timestamp: <b>{new Date(d.decided_at).toLocaleString()}</b></span>
                      </div>
                    </div>
                  )}

                  <div className="memory-meta">
                    <Avatar name={d.decided_by} size="sm" />
                    <span>
                      Decided by <strong>{d.decided_by}</strong> on {new Date(d.decided_at).toLocaleDateString()}
                    </span>
                  </div>
                </div>
                {i < filtered.length - 1 && <span className="timeline-line" />}
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default function App() {
  const [page, setPage] = useState<Page>(() => {
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      const tabParam = params.get("tab");
      const validPages: Page[] = ["Overview", "Check-In", "Alignment", "Decisions", "Team Memory"];
      if (tabParam && validPages.includes(tabParam as Page)) {
        return tabParam as Page;
      }
    }
    return "Overview";
  });
  const [menuOpen, setMenuOpen] = useState(false);
  const [setupMode, setSetupMode] = useState<"create" | "members" | null>(null);

  // Live state from FastAPI backend
  const [projects, setProjects] = useState<Project[]>([]);
  const [currentProjectId, setCurrentProjectId] = useState<string | null>(() => {
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      return params.get("project_id");
    }
    return null;
  });
  const [responses, setResponses] = useState<MemberResponse[]>([]);
  const [report, setReport] = useState<SynthesisReport | null>(null);
  const [analysisResult, setAnalysisResult] = useState<AlignmentWorkflowResult | null>(null);
  const [decisions, setDecisions] = useState<ConfirmedDecision[]>([]);
  const [activeUser] = useState<string>("Alex Morgan");

  // Loading & status states
  const [analyzing, setAnalyzing] = useState(false);
  const [recording, setRecording] = useState(false);
  const [isSeeding, setIsSeeding] = useState(false);
  const [executionMode, setExecutionMode] = useState<string>("MOCK_DETERMINISTIC");
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isLive, setIsLive] = useState(true);

  // Active project
  const currentProject = useMemo(() => {
    return projects.find((p) => p.id === currentProjectId) || projects[0] || null;
  }, [projects, currentProjectId]);

  const handleSelectProject = (id: string) => {
    setCurrentProjectId(id);
    if (typeof window !== "undefined") {
      const url = new URL(window.location.href);
      url.searchParams.set("project_id", id);
      window.history.replaceState(null, "", url.toString());
    }
  };

  // Load initial projects from backend
  const refreshProjects = async () => {
    try {
      setLoadError(null);
      const list = await apiClient.getProjects();
      setProjects(list);
      setIsLive(true);
      if (list.length > 0) {
        const params = new URLSearchParams(window.location.search);
        const qId = params.get("project_id");
        if (qId && list.some((p) => p.id === qId)) {
          setCurrentProjectId(qId);
        } else if (currentProjectId && list.some((p) => p.id === currentProjectId)) {
          // Keep current valid selection
        } else {
          setCurrentProjectId(list[0].id);
          const url = new URL(window.location.href);
          url.searchParams.set("project_id", list[0].id);
          window.history.replaceState(null, "", url.toString());
        }
      }
    } catch (err) {
      console.error("Failed to load projects from backend:", err);
      setIsLive(false);
      setLoadError(err instanceof Error ? err.message : "Unable to reach API backend.");
    }
  };

  useEffect(() => {
    refreshProjects();

    const handlePopState = () => {
      const params = new URLSearchParams(window.location.search);
      const qId = params.get("project_id");
      if (qId) {
        setCurrentProjectId(qId);
      }
      const tabParam = params.get("tab");
      const validPages: Page[] = ["Overview", "Check-In", "Alignment", "Decisions", "Team Memory"];
      if (tabParam && validPages.includes(tabParam as Page)) {
        setPage(tabParam as Page);
      }
    };
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  // When active project changes, load its responses, alignment, and decisions
  useEffect(() => {
    if (!currentProject) return;

    setAnalysisResult(null);
    setAnalysisError(null);

    // Load responses
    apiClient
      .getResponses(currentProject.id)
      .then((r) => setResponses(r))
      .catch(() => setResponses([]));

    // Load alignment report
    apiClient
      .getAlignmentReport(currentProject.id)
      .then((rep) => setReport(rep))
      .catch(() => setReport(null));

    // Load decisions
    apiClient
      .getDecisions(currentProject.id)
      .then((d) => setDecisions(d))
      .catch(() => setDecisions([]));
  }, [currentProject?.id]);

  // Phase 1: Create project handler
  const handleCreateProject = async (
    title: string,
    description: string,
    initialMembers: Array<{ name: string; role: string; email: string }>,
  ) => {
    const created = await apiClient.createProject({ title, description });
    for (const m of initialMembers) {
      try {
        await apiClient.addTeamMember(created.id, {
          name: m.name,
          role: m.role,
          email: m.email,
        });
      } catch (e) {
        console.warn("Failed to add member to new project:", e);
      }
    }
    await refreshProjects();
    setCurrentProjectId(created.id);
  };

  // Phase 1: Add member handler
  const handleAddMember = async (name: string, role: string, email: string) => {
    if (!currentProject) return;
    await apiClient.addTeamMember(currentProject.id, { name, role, email });
    const updated = await apiClient.getProject(currentProject.id);
    setProjects((cur) => cur.map((p) => (p.id === updated.id ? updated : p)));
  };

  // Phase 2: Submit Check-in
  const handleSubmitResponse = async (memberName: string, rawText: string) => {
    if (!currentProject) throw new Error("No active project");
    await apiClient.submitResponse(currentProject.id, {
      member_name: memberName,
      raw_text: rawText,
      source: "checkin_survey",
    });
    const updatedResponses = await apiClient.getResponses(currentProject.id);
    setResponses(updatedResponses);
  };

  // Phase 3: Run Analysis
  const handleRunAnalysis = async () => {
    if (!currentProject) return;
    setAnalyzing(true);
    setAnalysisError(null);
    try {
      const result = await apiClient.runAnalysis(currentProject.id);
      setAnalysisResult(result);
      setReport(result.synthesis_output);
      setExecutionMode(result.execution_mode || "MOCK_DETERMINISTIC");
    } catch (err: unknown) {
      const msg = err instanceof ApiError ? err.message : "Multi-agent analysis failed.";
      setAnalysisError(msg);
    } finally {
      setAnalyzing(false);
    }
  };

  // Phase 4: Record Decision
  const handleRecordDecision = async (
    resolutionId: string,
    action: "APPROVE" | "REJECT" | "MODIFY",
    customText?: string,
  ) => {
    if (!currentProject) return;
    setRecording(true);
    try {
      await apiClient.recordDecision(currentProject.id, {
        resolution_id: resolutionId,
        action,
        decision_text: customText || null,
        decided_by: activeUser,
      });
      const updated = await apiClient.getDecisions(currentProject.id);
      setDecisions(updated);
    } finally {
      setRecording(false);
    }
  };

  // Seed Demo Scenario (Alex, Sam, Taylor)
  const handleSeedDemoScenario = async () => {
    if (!currentProject) return;
    setIsSeeding(true);
    try {
      // Add Alex, Sam, Taylor if not present
      const existingNames = new Set(currentProject.members?.map((m) => m.name.toLowerCase()) || []);
      if (!existingNames.has("alex morgan")) {
        await apiClient.addTeamMember(currentProject.id, { name: "Alex Morgan", role: "Frontend Lead" });
      }
      if (!existingNames.has("sam rivera")) {
        await apiClient.addTeamMember(currentProject.id, { name: "Sam Rivera", role: "Backend Lead" });
      }
      if (!existingNames.has("taylor kim")) {
        await apiClient.addTeamMember(currentProject.id, { name: "Taylor Kim", role: "DevOps & QA" });
      }

      // Submit viewpoints
      await apiClient.submitResponse(currentProject.id, {
        member_name: "Alex Morgan",
        raw_text: "The project deadline is Saturday and I believe Taylor owns deployment. Frontend will be fully finished by Friday.",
        source: "demo_scenario",
      });
      await apiClient.submitResponse(currentProject.id, {
        member_name: "Sam Rivera",
        raw_text: "The project deadline is Sunday and we need full feature completion before launch.",
        source: "demo_scenario",
      });
      await apiClient.submitResponse(currentProject.id, {
        member_name: "Taylor Kim",
        raw_text: "I believe Alex owns deployment, and we must complete thorough testing before launching anything. A 24-hour test buffer is required.",
        source: "demo_scenario",
      });

      // Refresh responses and project
      const updatedProj = await apiClient.getProject(currentProject.id);
      setProjects((cur) => cur.map((p) => (p.id === updatedProj.id ? updatedProj : p)));
      const updatedResponses = await apiClient.getResponses(currentProject.id);
      setResponses(updatedResponses);

      // Trigger multi-agent analysis automatically!
      const res = await apiClient.runAnalysis(currentProject.id);
      setAnalysisResult(res);
      setReport(res.synthesis_output);
      setExecutionMode(res.execution_mode || "MOCK_DETERMINISTIC");
      setPage("Alignment");
    } catch (e) {
      console.error("Failed to seed demo scenario:", e);
    } finally {
      setIsSeeding(false);
    }
  };

  const navigate = (p: Page) => {
    setPage(p);
    setMenuOpen(false);
    if (typeof window !== "undefined") {
      const url = new URL(window.location.href);
      url.searchParams.set("tab", p);
      window.history.replaceState(null, "", url.toString());
    }
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  return (
    <div className={`app-shell ${menuOpen ? "menu-open" : ""}`}>
      <Sidebar
        page={page}
        setPage={navigate}
        onCreateProject={() => setSetupMode("create")}
        onManageTeam={() => setSetupMode("members")}
        activeUser={activeUser}
        decisionsCount={decisions.length}
      />
      {menuOpen && (
        <button
          className="menu-scrim"
          onClick={() => setMenuOpen(false)}
          aria-label="Close navigation"
        />
      )}
      <div className="main-shell">
        <Header
          project={currentProject}
          projects={projects}
          onSelectProject={handleSelectProject}
          onCreateProject={() => setSetupMode("create")}
          onManageTeam={() => setSetupMode("members")}
          menuOpen={menuOpen}
          setMenuOpen={setMenuOpen}
          executionMode={executionMode}
          isLive={isLive}
        />
        {loadError && (
          <div
            style={{
              margin: "12px 24px 0",
              padding: "10px 16px",
              background: "rgba(239, 68, 68, 0.12)",
              border: "1px solid rgba(239, 68, 68, 0.3)",
              borderRadius: "8px",
              color: "#f87171",
              fontSize: "13px",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            <span>
              ⚠️ <strong>Backend Connection Error:</strong> {loadError}
            </span>
            <button
              onClick={refreshProjects}
              style={{
                background: "rgba(239, 68, 68, 0.25)",
                border: "1px solid rgba(239, 68, 68, 0.4)",
                color: "#fff",
                padding: "4px 10px",
                borderRadius: "4px",
                fontSize: "12px",
                cursor: "pointer",
              }}
            >
              Retry
            </button>
          </div>
        )}
        <main>
          {page === "Overview" && (
            <Overview
              project={currentProject}
              responses={responses}
              report={report}
              decisions={decisions}
              setPage={navigate}
              onManageTeam={() => setSetupMode("members")}
              onSeedDemo={handleSeedDemoScenario}
              isSeeding={isSeeding}
            />
          )}
          {page === "Check-In" && (
            <CheckIn
              key={currentProject?.id}
              project={currentProject}
              responses={responses}
              onComplete={() => navigate("Alignment")}
              onSubmitResponse={handleSubmitResponse}
            />
          )}
          {page === "Alignment" && (
            <Alignment
              project={currentProject}
              analysisResult={analysisResult}
              report={report}
              responses={responses}
              onRunAnalysis={handleRunAnalysis}
              analyzing={analyzing}
              error={analysisError}
              onStartCheckIn={() => navigate("Check-In")}
              setPage={navigate}
            />
          )}
          {page === "Decisions" && (
            <Decisions
              project={currentProject}
              report={report}
              decisions={decisions}
              onRecordDecision={handleRecordDecision}
              recording={recording}
              activeUser={activeUser}
            />
          )}
          {page === "Team Memory" && (
            <TeamMemory project={currentProject} decisions={decisions} />
          )}
        </main>
      </div>
      {setupMode && (
        <ProjectSetupModal
          mode={setupMode}
          project={currentProject}
          onClose={() => setSetupMode(null)}
          onCreate={handleCreateProject}
          onAddMember={handleAddMember}
        />
      )}
    </div>
  );
}
