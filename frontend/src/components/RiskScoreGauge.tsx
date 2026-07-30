import type { RiskTier } from "../lib/types";

interface Props {
  score: number;
  tier: RiskTier;
  size?: "small" | "large";
}

export function RiskScoreGauge({ score, tier, size = "large" }: Props) {
  const radius = 54;
  const circumference = 2 * Math.PI * radius;
  const progress = Math.max(0, Math.min(100, score)) / 100;
  return (
    <div className={`score-gauge score-gauge--${size}`} aria-label={`Risk score ${score} out of 100, ${tier} risk`}>
      <svg viewBox="0 0 128 128" role="img">
        <circle className="score-gauge__track" cx="64" cy="64" r={radius} />
        <circle
          className={`score-gauge__progress tier-stroke--${tier}`}
          cx="64"
          cy="64"
          r={radius}
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - progress)}
        />
      </svg>
      <div className="score-gauge__label">
        <strong>{Math.round(score)}</strong>
        <span>/ 100</span>
      </div>
    </div>
  );
}
