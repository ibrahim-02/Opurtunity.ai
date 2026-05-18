type Props = {
  percent: number;
  size?: number;
};

export function MatchCircle({ percent, size = 64 }: Props) {
  const stroke = 5;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (percent / 100) * circumference;
  const color = percent >= 85 ? "#10b981" : percent >= 70 ? "#22c55e" : percent >= 50 ? "#f59e0b" : "#ef4444";

  return (
    <div className="flex flex-col items-center gap-1">
      <div className="relative" style={{ width: size, height: size }}>
        <svg width={size} height={size} className="-rotate-90">
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            stroke="#e4e4e7"
            strokeWidth={stroke}
            fill="none"
          />
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            stroke={color}
            strokeWidth={stroke}
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            strokeLinecap="round"
            fill="none"
            style={{ transition: "stroke-dashoffset 0.6s ease" }}
          />
        </svg>
        <div
          className="absolute inset-0 grid place-items-center text-sm font-semibold"
          style={{ color }}
        >
          {percent}%
        </div>
      </div>
      <span className="text-xs text-zinc-500">Match</span>
    </div>
  );
}
