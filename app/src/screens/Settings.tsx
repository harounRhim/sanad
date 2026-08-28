import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useSettings, type Theme } from "../state/SettingsContext";
import { useAuth } from "../state/AuthContext";
import { RECITERS } from "../lib/reciters";
import { isAudioConfigured } from "../lib/audio";
import { resetOnboarding } from "../lib/onboarding";

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 py-3.5">
      <span className="text-sm font-medium">{label}</span>
      {children}
    </div>
  );
}

function Group({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mb-5">
      <h2 className="mb-1 px-1 text-xs font-semibold uppercase tracking-wide text-brand-muted">
        {title}
      </h2>
      <div className="divide-y divide-brand-muted/10 rounded-2xl bg-brand-surface px-4 shadow-soft dark:bg-brand-darkSurface">
        {children}
      </div>
    </section>
  );
}

export default function Settings() {
  const s = useSettings();
  const auth = useAuth();
  const navigate = useNavigate();

  return (
    <div className="p-5">
      <h1 className="mb-4 text-xl font-bold">Settings</h1>

      <Group title="Profile">
        <div className="flex items-center gap-3 py-3.5">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-brand-emerald text-lg font-bold text-white">
            {(auth.displayName ?? "?").charAt(0).toUpperCase()}
          </div>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold">{auth.displayName ?? "—"}</p>
            <p className="truncate text-xs text-brand-muted dark:text-brand-darkMuted">
              {auth.user?.email}
            </p>
          </div>
        </div>
        <ChangeNameRow />
      </Group>

      <Group title="Account">
        <ChangeEmailRow />
        <Row label="Session">
          <button
            onClick={() => auth.signOut()}
            className="rounded-lg bg-brand-red/10 px-3 py-1.5 text-xs font-semibold text-brand-red"
          >
            Sign out
          </button>
        </Row>
      </Group>

      <Group title="Appearance">
        <Row label="Theme">
          <div className="inline-flex rounded-lg bg-brand-muted/10 p-1">
            {(["system", "light", "dark"] as Theme[]).map((t) => (
              <button
                key={t}
                onClick={() => s.set("theme", t)}
                className={`rounded-md px-3 py-1 text-xs font-semibold capitalize ${
                  s.theme === t ? "bg-brand-emerald text-white" : "text-brand-muted"
                }`}
              >
                {t}
              </button>
            ))}
          </div>
        </Row>
        <Row label={`Arabic font size (${Math.round(s.fontScale * 100)}%)`}>
          <input
            type="range"
            min={0.8}
            max={1.8}
            step={0.1}
            value={s.fontScale}
            onChange={(e) => s.set("fontScale", Number(e.target.value))}
            className="w-40 accent-brand-emerald"
          />
        </Row>
        <div className="py-3">
          <p className="quran text-right" style={{ fontSize: `${1.8 * s.fontScale}rem` }}>
            بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ
          </p>
        </div>
      </Group>

      <Group title="Reading">
        <Row label="Tajweed coloring">
          <Toggle on={s.tajweed} onClick={() => s.set("tajweed", !s.tajweed)} />
        </Row>
        <Row label="Autoplay next ayah">
          <Toggle on={s.autoplay} onClick={() => s.set("autoplay", !s.autoplay)} />
        </Row>
        <Row label="Default reciter">
          <select
            value={s.defaultReciter}
            onChange={(e) => s.set("defaultReciter", e.target.value)}
            className="max-w-[55%] rounded-lg border border-brand-muted/20 bg-transparent px-2 py-1.5 text-sm"
          >
            {RECITERS.map((r) => (
              <option key={r.key} value={r.key}>
                {r.name}
              </option>
            ))}
          </select>
        </Row>
      </Group>

      <Group title="Help">
        <Row label="Replay the app guide">
          <button
            onClick={() => {
              resetOnboarding();
              navigate("/");
            }}
            className="rounded-lg bg-brand-emerald/10 px-3 py-1.5 text-xs font-semibold text-brand-emerald dark:text-brand-goldLight"
          >
            Show me again
          </button>
        </Row>
        <Row label="Tajweed colour guide">
          <a href="/legend" className="text-xs font-semibold text-brand-emerald underline dark:text-brand-goldLight">
            Open legend →
          </a>
        </Row>
      </Group>

      <Group title="About">
        <Row label="Audio source">
          <span className="text-xs text-brand-muted">
            {isAudioConfigured ? "Configured" : "Not set (VITE_AUDIO_BASE_URL)"}
          </span>
        </Row>
        <Row label="App">
          <span className="text-xs text-brand-muted">Sanad · MVP</span>
        </Row>
      </Group>
    </div>
  );
}

/** Inline "edit your name" row — writes to user_metadata (instant, no email
 * confirm). Prefilled with the current display name. */
function ChangeNameRow() {
  const auth = useAuth();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState(auth.displayName ?? "");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (busy || !name.trim()) return;
    setBusy(true);
    setMsg(null);
    try {
      const { error } = await auth.updateName(name);
      if (error) setMsg({ ok: false, text: error });
      else {
        setMsg({ ok: true, text: "Saved." });
        setOpen(false);
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="py-3.5">
      <div className="flex items-center justify-between gap-4">
        <span className="text-sm font-medium">Name</span>
        <button
          onClick={() => {
            setName(auth.displayName ?? "");
            setOpen((o) => !o);
            setMsg(null);
          }}
          className="rounded-lg bg-brand-muted/10 px-3 py-1.5 text-xs font-semibold text-brand-muted dark:text-brand-darkMuted"
        >
          {open ? "Cancel" : "Edit"}
        </button>
      </div>
      {open && (
        <form onSubmit={submit} className="mt-3 flex gap-2">
          <input
            type="text"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Your name"
            className="min-w-0 flex-1 rounded-lg border border-brand-muted/20 bg-transparent px-3 py-2 text-sm outline-none focus:border-brand-emerald"
          />
          <button
            type="submit"
            disabled={busy}
            className="rounded-lg bg-brand-emerald px-4 py-2 text-xs font-semibold text-white disabled:opacity-50"
          >
            {busy ? "…" : "Save"}
          </button>
        </form>
      )}
      {msg && (
        <p className={`mt-2 text-xs ${msg.ok ? "text-brand-emerald" : "text-brand-red"}`}>
          {msg.text}
        </p>
      )}
    </div>
  );
}

/** Inline expandable "Change email" row — supabase.auth.updateUser({email})
 * sends confirmation links to BOTH addresses; the change lands only after
 * they're clicked, so success copy says "check your inboxes", not "done". */
function ChangeEmailRow() {
  const auth = useAuth();
  const [open, setOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setMsg(null);
    try {
      const { error } = await auth.updateEmail(email);
      if (error) setMsg({ ok: false, text: error });
      else {
        setMsg({ ok: true, text: "Confirmation links sent — check both inboxes to finish." });
        setEmail("");
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="py-3.5">
      <div className="flex items-center justify-between gap-4">
        <span className="text-sm font-medium">Email</span>
        <button
          onClick={() => {
            setOpen((o) => !o);
            setMsg(null);
          }}
          className="rounded-lg bg-brand-muted/10 px-3 py-1.5 text-xs font-semibold text-brand-muted dark:text-brand-darkMuted"
        >
          {open ? "Cancel" : "Change email"}
        </button>
      </div>
      {open && (
        <form onSubmit={submit} className="mt-3 flex gap-2">
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="new@email.com"
            className="min-w-0 flex-1 rounded-lg border border-brand-muted/20 bg-transparent px-3 py-2 text-sm outline-none focus:border-brand-emerald"
          />
          <button
            type="submit"
            disabled={busy}
            className="rounded-lg bg-brand-emerald px-4 py-2 text-xs font-semibold text-white disabled:opacity-50"
          >
            {busy ? "…" : "Send"}
          </button>
        </form>
      )}
      {msg && (
        <p className={`mt-2 text-xs ${msg.ok ? "text-brand-emerald" : "text-brand-red"}`}>
          {msg.text}
        </p>
      )}
    </div>
  );
}

function Toggle({ on, onClick }: { on: boolean; onClick: () => void }) {
  return (
    <button
      role="switch"
      aria-checked={on}
      onClick={onClick}
      className={`relative h-6 w-11 rounded-full transition-colors ${
        on ? "bg-brand-emerald" : "bg-brand-muted/30"
      }`}
    >
      <span
        className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition-transform ${
          on ? "translate-x-5" : "translate-x-0.5"
        }`}
      />
    </button>
  );
}
