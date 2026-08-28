// Reciter catalogue. `key` matches ayah_audio.reciter in the DB.
// Generated from Data/audio/data/reciters.json (maher_almuaiqly omitted — no audio).
// The Reciters screen can additionally filter this against reciters actually
// present in ayah_audio.

export type ReciterStyle = "Murattal" | "Mujawwad" | "Teacher" | "Warsh";

export interface Reciter {
  key: string;
  name: string;
  style: ReciterStyle;
}

export const RECITERS: Reciter[] = [
  { key: 'abdul_basit_murattal', name: 'Abdul Basit Murattal', style: 'Murattal' },
  { key: 'abdullaah_3awwaad_al_juhaynee', name: 'Abdullaah Awwaad Al-Juhaynee', style: 'Murattal' },
  { key: 'abdullah_basfar', name: 'Abdullah Basfar', style: 'Murattal' },
  { key: 'abdulsamad', name: 'Abdul Samad', style: 'Murattal' },
  { key: 'abdurrahmaan_as_sudais', name: 'Abdurrahmaan As-Sudais', style: 'Murattal' },
  { key: 'abu_bakr_ash_shaatree', name: 'Abu Bakr Ash-Shaatree', style: 'Murattal' },
  { key: 'alafasy', name: 'Mishary Alafasy', style: 'Murattal' },
  { key: 'ali_jaber', name: 'Ali Jaber', style: 'Murattal' },
  { key: 'ayman_sowaid', name: 'Ayman Sowaid', style: 'Murattal' },
  { key: 'banna', name: 'Mahmoud Al-Banna', style: 'Murattal' },
  { key: 'fares_abbad', name: 'Fares Abbad', style: 'Murattal' },
  { key: 'ghamadi', name: 'Saad Al-Ghamadi', style: 'Murattal' },
  { key: 'hani_rifai', name: 'Hani Ar-Rifai', style: 'Murattal' },
  { key: 'hudhaify', name: 'Ali Al-Hudhaify', style: 'Murattal' },
  { key: 'husary', name: 'Mahmoud Al-Husary', style: 'Murattal' },
  { key: 'husary_mujawwad', name: 'Mahmoud Al-Husary', style: 'Mujawwad' },
  { key: 'hussary.teacher', name: 'Al-Husary (Teacher)', style: 'Teacher' },
  { key: 'ibrahim_akhdar', name: 'Ibrahim Al-Akhdar', style: 'Murattal' },
  { key: 'minshawy_mujawwad', name: 'Mohamed Al-Minshawy', style: 'Mujawwad' },
  { key: 'minshawy_murattal', name: 'Mohamed Al-Minshawy', style: 'Murattal' },
  { key: 'minshawy_teacher', name: 'Al-Minshawy (Teacher)', style: 'Teacher' },
  { key: 'mostafa_ismail', name: 'Mostafa Ismail', style: 'Murattal' },
  { key: 'muhammad_jibreel', name: 'Muhammad Jibreel', style: 'Murattal' },
  { key: 'muhsin_al_qasim', name: 'Muhsin Al-Qasim', style: 'Murattal' },
  { key: 'nasser_alqatami', name: 'Nasser Al-Qatami', style: 'Murattal' },
  { key: 'saood_ash_shuraym', name: 'Saood Ash-Shuraym', style: 'Murattal' },
  { key: 'tunaiji', name: 'Khalifa Al-Tunaiji', style: 'Murattal' },
  { key: 'warsh_husary', name: 'Al-Husary (Warsh)', style: 'Warsh' },
  { key: 'warsh_yassin', name: 'Yassin Al-Jazairi (Warsh)', style: 'Warsh' },
  { key: 'yasser_ad_dussary', name: 'Yasser Ad-Dussary', style: 'Murattal' },
];

export const DEFAULT_RECITER = "alafasy";

export const RECITER_BY_KEY: Record<string, Reciter> = Object.fromEntries(
  RECITERS.map((r) => [r.key, r])
);

export function reciterName(key: string): string {
  return RECITER_BY_KEY[key]?.name ?? key;
}
