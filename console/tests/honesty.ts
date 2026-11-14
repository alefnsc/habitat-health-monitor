// Honesty-lint rule functions. Shared by copy.test.ts (console) and the camera tests (C12b).
// Each rule returns true when the string VIOLATES the rule.

export const ruleCalories = (s: string): boolean => /\b(kcal|calories?)\b/i.test(s);

export const ruleEnergyBalance = (s: string): boolean =>
  /\bnet calories\b|\bcalories burned\b|\bburn(s|ed|ing)?\b|\bdeficit\b|\bsurplus\b|\benergy balance\b|\bbalance\b|\blose weight\b|\bdiet\b/i.test(
    s,
  );

export const ruleMealPlan = (s: string): boolean =>
  /\bmeal plan\b|\byou should eat\b|\brecommended menu\b/i.test(s);

export const ruleDiagnosis = (s: string): boolean => /diagnos/i.test(s);

// A number followed by a drug-style unit (mg, mcg, ml, unit, units), except mg/dL.
export const ruleTreatmentDose = (s: string): boolean =>
  /\b\d+(\.\d+)?\s*(mg(?!\/)|mcg|ml|units?)\b/i.test(s);

export const ruleBrand = (s: string): boolean =>
  /polar|garmin|apple|oura|withings|google|lightstreamer|vocaid|omron/i.test(s);

export const ruleNonEnglish = (s: string): boolean => /[ãõçáéíóúâêôà]/i.test(s);

export const ruleCameraWording = (s: string): boolean => /measured|validated|accurate/i.test(s);

// Extract string literals from TypeScript source text (single, double, template). Skips comments.
export function stringLiterals(src: string): string[] {
  const out: string[] = [];
  let i = 0;
  while (i < src.length) {
    const c = src[i];
    if (c === "/" && src[i + 1] === "/") {
      while (i < src.length && src[i] !== "\n") i++;
    } else if (c === "/" && src[i + 1] === "*") {
      i = src.indexOf("*/", i + 2);
      if (i < 0) break;
      i += 2;
    } else if (c === '"' || c === "'" || c === "`") {
      const q = c;
      let j = i + 1;
      let buf = "";
      while (j < src.length && src[j] !== q) {
        if (src[j] === "\\") {
          buf += src[j + 1] ?? "";
          j += 2;
        } else {
          buf += src[j++];
        }
      }
      out.push(buf);
      i = j + 1;
    } else {
      i++;
    }
  }
  return out;
}
