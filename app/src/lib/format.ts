/** Zero-pad a number to a fixed width (e.g. pad(5, 3) -> "005"). */
export function pad(n: number, width = 3): string {
  return String(n).padStart(width, "0");
}

const EASTERN = ["٠", "١", "٢", "٣", "٤", "٥", "٦", "٧", "٨", "٩"];

/** Render a number using Eastern-Arabic-Indic digits (for ayah ornaments). */
export function toArabicDigits(n: number): string {
  return String(n)
    .split("")
    .map((c) => (c >= "0" && c <= "9" ? EASTERN[Number(c)] : c))
    .join("");
}

export function ref(surah: number, ayah: number): string {
  return `${surah}:${ayah}`;
}
