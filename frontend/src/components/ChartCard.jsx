export default function ChartCard({ title, subtitle, children, className = "" }) {
  return (
    <div className={`card p-4 ${className}`}>
      <div className="mb-3">
        <div className="font-semibold">{title}</div>
        {subtitle && <div className="text-xs text-slate-500 mt-0.5">{subtitle}</div>}
      </div>
      <div className="h-[260px]">{children}</div>
    </div>
  );
}
