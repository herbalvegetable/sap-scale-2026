import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const ACRONYMS = new Set([
  "SLA", "KYC", "PEP", "SAR", "FATF", "OFAC", "EU", "UK", "USD", "EUR", "CAD", "APAC", "NA", "GCRO", "FCU",
]);

/** Known product labels that should never appear as raw codes. */
const LABEL_MAP: Record<string, string> = {
  clear: "Clear",
  escalate_tier2: "Escalate to Tier 2",
  request_kyc: "Request Additional KYC/Info",
  draft_sar: "Draft SAR",
  entity_risk: "Entity risk profile",
  transaction_behaviour: "Transaction behaviour",
  geographic_risk: "Geographic risk",
  behavioural_deviation: "Behavioural deviation",
  regulatory_sensitivity: "Regulatory sensitivity",
  generated: "Generated",
  reviewed: "Reviewed",
  approved: "Approved",
  overridden: "Declined",
  actioned: "Actioned",
  further_info_requested: "Further information requested",
  open: "Open",
  investigating: "Investigating",
  closed: "Closed",
  closed_timeout: "Closed – Closed due to expired review timeline",
  low: "Low",
  medium: "Medium",
  high: "High",
  factor: "Risk factor",
  evidence: "Evidence",
  precedent: "Precedent",
  policy: "Policy",
  case_field: "Case detail",
  chart: "Chart",
  "SAR-CANDIDATE-APAC": "SAR candidate — Asia Pacific",
  "PATTERN-REVIEW-EU": "Pattern review — Europe",
  "KYC-REFRESH-APAC": "KYC refresh — Asia Pacific",
  "THRESHOLD-ATTEST-EU": "Threshold attestation — Europe",
  "STANDARD-REVIEW-APAC": "Standard review — Asia Pacific",
  "VELOCITY-REVIEW-NA": "Velocity review — North America",
  "GENERAL-TRIAGE": "General triage",
  "SAR-01": "Sanctions / high-risk SAR path",
  "ESC-01": "Tier-2 escalation path",
  "KYC-01": "Additional KYC path",
  "CLR-01": "Clearance path",
  "KYC-DEFAULT": "Default KYC path",
  "CONF-ABSTAIN-01": "Low-confidence abstention",
  COMPANY_RISK_PROFILES: "Company risk profiles",
  COMPANY: "Company screening",
  TRANSACTIONS: "Transaction records",
  COUNTRIES: "Country risk data",
  TRANSACTION_BASELINES: "Transaction baselines",
  COMPLIANCE_CASES: "Compliance case history",
  "TRANSACTION activity + TRANSACTION_BASELINES": "Transaction activity and baselines",
  "Mock case-data store": "Case evidence store",
  "Mock case-data store (precedent cases)": "Precedent case evidence",
  "RiskAssess scoring engine": "RiskAssess scoring",
  "RiskAssess factor evidence": "Risk factor evidence",
  "COMPANY screening flags": "Company screening",
  fatf_risk: "Destination country risk",
  amount_ratio: "Amount versus baseline",
  risk_rating: "Entity risk rating",
  sanctions_match: "Sanctions screening",
  prior_cases: "Prior compliance cases",
  beneficial_owner_layers: "Beneficial ownership layers",
  new_corridor: "New corridor",
  THRESHOLD_BREACH: "Threshold breach",
};

/** Convert codes / snake_case / kebab-case into readable English labels. */
export function humanizeLabel(value: string): string {
  if (!value) return value;
  const mapped = LABEL_MAP[value] ?? LABEL_MAP[value.toLowerCase()];
  if (mapped) return mapped;

  return value
    .replace(/\+/g, " ")
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/[_./-]+/g, " ")
    .trim()
    .split(/\s+/)
    .map((word) => {
      if (!word) return word;
      if (/^&+$/.test(word)) return word;
      const upper = word.toUpperCase();
      if (ACRONYMS.has(upper)) return upper;
      if (/^\d+$/.test(word)) return word;
      return word.charAt(0).toUpperCase() + word.slice(1).toLowerCase();
    })
    .join(" ");
}
