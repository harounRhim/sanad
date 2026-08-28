// The 18 Tajweed rules — keys EXACTLY match tajweed_segments.rule in the DB.
// Colors come from docs/CLAUDE_DESIGN_IDENTITY_PROMPT.md.

export type RuleGroup =
  | "Madd"
  | "Ghunnah & Idghām"
  | "Ikhfā & Iqlāb"
  | "Qalqalah"
  | "Special";

export interface TajweedRule {
  key: string;
  en: string;
  ar: string;
  color: string;
  group: RuleGroup;
  desc: string;
}

export const TAJWEED_RULES: TajweedRule[] = [
  { key: "madd_2", en: "Natural prolongation (2)", ar: "مدّ طبيعي", color: "#E8A33D", group: "Madd", desc: "Elongate the vowel for 2 counts." },
  { key: "madd_246", en: "Prolongation (2/4/6)", ar: "مدّ عارض", color: "#F2C14E", group: "Madd", desc: "Elongate 2, 4, or 6 counts (reader's choice)." },
  { key: "madd_6", en: "Necessary prolongation (6)", ar: "مدّ لازم", color: "#E5392B", group: "Madd", desc: "Obligatory 6-count elongation." },
  { key: "madd_munfasil", en: "Separate prolongation", ar: "مدّ منفصل", color: "#F58B3C", group: "Madd", desc: "Elongation across two words (4–5 counts)." },
  { key: "madd_muttasil", en: "Connected prolongation", ar: "مدّ متصل", color: "#E5662E", group: "Madd", desc: "Elongation within one word (4–5 counts)." },
  { key: "ghunnah", en: "Nasalization", ar: "غُنّة", color: "#1E9E8A", group: "Ghunnah & Idghām", desc: "Nasal sound held for 2 counts." },
  { key: "idghaam_ghunnah", en: "Merging with ghunnah", ar: "إدغام بغُنّة", color: "#2BB673", group: "Ghunnah & Idghām", desc: "Merge the nūn/tanwīn with nasalization." },
  { key: "idghaam_no_ghunnah", en: "Merging without ghunnah", ar: "إدغام بغير غُنّة", color: "#7FB069", group: "Ghunnah & Idghām", desc: "Merge without any nasalization." },
  { key: "idghaam_shafawi", en: "Labial merging", ar: "إدغام شفوي", color: "#4C9A7A", group: "Ghunnah & Idghām", desc: "Mīm merges into a following mīm." },
  { key: "idghaam_mutajanisayn", en: "Merging (similar)", ar: "إدغام متجانسين", color: "#5FA8A0", group: "Ghunnah & Idghām", desc: "Merge two letters of the same articulation point." },
  { key: "idghaam_mutaqaribayn", en: "Merging (close)", ar: "إدغام متقاربين", color: "#6FB3AB", group: "Ghunnah & Idghām", desc: "Merge two letters of close articulation points." },
  { key: "ikhfa", en: "Hiding", ar: "إخفاء", color: "#3E78B2", group: "Ikhfā & Iqlāb", desc: "Hide the nūn/tanwīn with light nasalization." },
  { key: "ikhfa_shafawi", en: "Labial hiding", ar: "إخفاء شفوي", color: "#5B8FD6", group: "Ikhfā & Iqlāb", desc: "Hide mīm sākinah before bāʾ." },
  { key: "iqlab", en: "Conversion", ar: "إقلاب", color: "#7E57C2", group: "Ikhfā & Iqlāb", desc: "Convert nūn/tanwīn into a hidden mīm before bāʾ." },
  { key: "qalqalah", en: "Echoing", ar: "قلقلة", color: "#C2407A", group: "Qalqalah", desc: "Bouncing/echoing sound on a sākin letter." },
  { key: "hamzat_wasl", en: "Connecting hamza", ar: "همزة وصل", color: "#9AA0A6", group: "Special", desc: "Pronounced only when starting; dropped when connecting." },
  { key: "lam_shamsiyyah", en: "Assimilated lām", ar: "لام شمسية", color: "#B0883B", group: "Special", desc: "The lām of 'al-' is silent and assimilated." },
  { key: "silent", en: "Silent letter", ar: "حرف لا يُنطق", color: "#C4C7CC", group: "Special", desc: "Written but not pronounced." },
];

export const RULE_BY_KEY: Record<string, TajweedRule> = Object.fromEntries(
  TAJWEED_RULES.map((r) => [r.key, r])
);

export const RULE_GROUPS: RuleGroup[] = [
  "Madd",
  "Ghunnah & Idghām",
  "Ikhfā & Iqlāb",
  "Qalqalah",
  "Special",
];

export function ruleColor(key: string): string {
  return RULE_BY_KEY[key]?.color ?? "#C9A227";
}
