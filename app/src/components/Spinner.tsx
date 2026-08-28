export default function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16 text-brand-muted dark:text-brand-darkMuted">
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-brand-emerald/30 border-t-brand-emerald" />
      {label && <p className="text-sm">{label}</p>}
    </div>
  );
}
