// @vitest-environment jsdom
// D45 signals: the wording model and the screen's cards, from hub-shaped signal objects.
import { afterEach, describe, expect, test, vi } from "vitest";
import type { Prompt, Signal, SignalsBody } from "../src/contract";
import { setCurrentCrew } from "../src/crew";
import { fmt, groupOf, headline, lagLines, limitLines, missingLines, notableCounts, selfCheckFor } from "../src/model/signals";
import { renderSignals, renderSignalsBody } from "../src/views/signals";
import { renderPanel } from "../src/views/panel";
import type { PanelSource } from "../src/views/panel/source";
import { topBar } from "../src/views/panel/topbar";

// uPlot draws on a canvas, which jsdom does not have: the panel test only checks the top bar.
vi.mock("uplot", () => ({
  default: class {
    static tzDate(d: Date) {
      return d;
    }
    destroy() {}
    setData() {}
    setSize() {}
  },
}));

const NOW = Date.parse("2026-11-20T10:00:00Z");

const sig = (over: Partial<Signal> = {}): Signal => ({
  id: "rest_hr_baseline", kind: "baseline", crew: "crew-a", state: "steady",
  headline_key: "signals.baseline.inside", value: { estimate: 57, low: 54.03, high: 59.97, unit: "bpm", per: null },
  method: { name: "own_baseline", ref: "median and MAD", alpha: null, n: 14, min_n: 7,
    window_start: "2026-11-06T10:00:00.000Z", window_end: "2026-11-20T10:00:00.000Z", coverage: null },
  inputs: [{ ind: "hr", src: "hobby", dev: "RING", node: "ring-1", n: 1000, first_at: "2026-11-06T03:00:00.000Z",
    last_at: "2026-11-20T09:00:00.000Z", oldest_age_s: 3600 }],
  missing: [], limits: ["signals.limit.ringEstimate"], reference: null, replay: false,
  series: [["2026-11-18T10:00:00.000Z", 56], ["2026-11-19T10:00:00.000Z", 57], ["2026-11-20T10:00:00.000Z", 57]],
  pairs: [], can_trigger: true, detail: {}, ...over,
});

const cabinPair = (over: Partial<Signal> = {}): Signal => sig({
  id: "cabin_vs_earth", kind: "lagged_pair", crew: null, value: null, headline_key: "signals.pair.rho",
  method: { ...sig().method, name: "spearman_fisher_z", ref: "Spearman", n: 0, min_n: 20 },
  limits: ["signals.limit.earthReference"],
  inputs: [{ ...sig().inputs[0], ind: "earth_temp", src: "ref", dev: "WEATHER" }],
  detail: { lags: [{ lag_h: 0, n: 30, rho: 0.41, low: 0.06, high: 0.67 }, { lag_h: 1, n: 29, rho: null, low: null, high: null },
    { lag_h: 2, n: 5, rho: null, low: null, high: null }, { lag_h: 3, n: 0, rho: null, low: null, high: null }] },
  pairs: [["2026-11-20T06:00:00.000Z", 11.2, 21.5, 0], ["2026-11-20T07:00:00.000Z", 11.9, 21.7, 1]],
  ...over,
});

const prompt = (over: Record<string, unknown> = {}, trigger: Record<string, unknown> | null = {}): Prompt => ({
  id: 9, kind: "signal_body", crew: "crew-a", status: "open", created_at: "x", asks: ["symptom", "mood"],
  trigger_reading_id: null, rule_id: null,
  trigger: trigger === null ? null : { signal_id: "rest_hr_baseline", state: "notable", headline_key: "x", value: null,
    inputs: [], limits: [], reference: null, replay: false, at: "x", ...trigger },
  ...over,
}) as Prompt;

describe("signals model", () => {
  test("baseline, trend, time-to-limit and missing wording", () => {
    expect(headline(sig())).toBe("Inside your own usual range: 57.0 bpm (usual 54.0 to 60.0).");
    expect(headline(sig({ kind: "trend", headline_key: "signals.trend.up",
      value: { estimate: 0.5, low: 0.31, high: 0.72, unit: "C", per: "h" } })))
      .toBe("Trend up: 0.50 °C per hour (interval 0.31 to 0.72).");
    expect(headline(sig({ kind: "trend", headline_key: "signals.trend.down",
      value: { estimate: -0.5, low: -0.72, high: -0.31, unit: "C", per: "h" } })))
      .toBe("Trend down: −0.50 °C per hour (interval −0.72 to −0.31).");
    expect(headline(sig({ kind: "trend", headline_key: "signals.trend.flat",
      value: { estimate: 0.01, low: -0.2, high: 0.22, unit: "kg", per: "day" } })))
      .toBe("No clear trend: 0.01 kg per day (interval −0.20 to 0.22).");
    expect(headline(sig({ id: "cabin_rh_ttl", kind: "time_to_limit", crew: null, headline_key: "signals.ttl.reaches",
      value: { estimate: 3.8, low: 3.4, high: 4.3, unit: "h", per: null },
      reference: { rule_id: "cabin_health_box_rh", source_kind: "nasa_std", limit: 75 },
      inputs: [{ ...sig().inputs[0], ind: "cabin_rh" }] })))
      .toBe("At this rate, reaches 75.0 % in 3.40 to 4.30 h, if nothing changes.");
    const nd = sig({ state: "not_enough_data", headline_key: "signals.nodata", value: null,
      missing: [{ key: "signals.missing.priorDays", need: 7, have: 4 }] });
    expect(headline(nd)).toBe("Not enough data yet.");
    expect(missingLines(nd)).toEqual(["Needs 7 earlier days for your usual range; has 4."]);
  });

  test("daily pair headlines: rank correlation with its n, or too few pairs", () => {
    const pair = sig({ id: "training_vs_rest_hr", kind: "lagged_pair", headline_key: "signals.pair.rho",
      value: { estimate: 0.41, low: 0.06, high: 0.67, unit: "rho", per: null },
      method: { ...sig().method, n: 30 } });
    expect(headline(pair)).toBe(
      "Side by side: rank correlation 0.41 (interval 0.06 to 0.67), 30 pairs. Association in your own data, not cause.");
    expect(headline(sig({ ...pair, headline_key: "signals.pair.few", value: null, method: { ...sig().method, n: 5 } })))
      .toBe("Side by side: 5 pairs, too few pairs to say anything.");
  });

  test("cabin_vs_earth headline: no placeholder left, n from its lags, no false 0 pairs", () => {
    for (const key of ["signals.pair.rho", "signals.pair.few"]) {
      const h = headline(cabinPair({ headline_key: key }));
      expect(h).not.toContain("{");
      expect(h).not.toContain(" 0 pairs");
      expect(h).toBe("Side by side at 0 to 3 h lags: 64 pairs across the lags; see each lag below. "
        + "Association in your own data, not cause.");
    }
  });

  test("lag lines name every lag and pick none", () => {
    expect(lagLines(cabinPair()).slice(0, 2)).toEqual([
      "0 h later: 30 pairs, rank correlation 0.41 (interval 0.06 to 0.67).",
      "1 h later: 29 pairs, too few to say anything.",
    ]);
  });

  test("groups, number format, notable counts kept apart for real and replay", () => {
    expect(groupOf("cabin_rh_ttl")).toBe("cabin");
    expect(groupOf("water_14d")).toBe("food");
    expect(fmt(-0.123)).toBe("−0.12");
    const body: SignalsBody = { crew: null, at: "x", signals: [
      sig({ state: "notable" }), sig(), sig({ crew: "crew-c", state: "notable", replay: true }),
      sig({ crew: "crew-a", state: "notable", replay: true }),
    ] };
    expect(notableCounts(body)).toEqual({ real: 1, replay: 2 });
    expect(notableCounts(null)).toEqual({ real: 0, replay: 0 });
  });

  test("open self-check: only an open signal prompt for this crew and this signal", () => {
    expect(selfCheckFor([prompt()], sig())?.id).toBe(9);
    expect(selfCheckFor([prompt()], sig({ crew: "crew-c" }))).toBeUndefined();
    expect(selfCheckFor([prompt({ status: "answered" })], sig())).toBeUndefined();
    expect(selfCheckFor([prompt({ kind: "morning" })], sig())).toBeUndefined();
    expect(selfCheckFor([prompt({}, { signal_id: "sleep_baseline" })], sig())).toBeUndefined();
    expect(selfCheckFor([prompt({}, null)], sig())).toBeUndefined();
    expect(selfCheckFor([prompt({ kind: "signal_cabin", crew: null })], sig({ crew: null }))?.id).toBe(9);
  });

  test("reference limits name the weather model and the US Lab item only", () => {
    const [earth, iss] = limitLines(sig({ limits: ["signals.limit.earthReference", "signals.limit.issTelemetry"] }));
    expect(earth).toContain("weather-model values");
    expect(earth).toContain("coarse grid cell");
    expect(earth).toContain("not a station");
    expect(earth).toContain("not the bench itself");
    expect(iss).toContain("US Lab ppCO2 item only");
    expect(iss).not.toContain("Node 3");
  });
});

describe("signals screen", () => {
  test("cards per group, not-enough-data greyed and shown, replay chips", () => {
    const root = document.createElement("div");
    const body: SignalsBody = { crew: "crew-a", at: "x", signals: [
      sig({ state: "notable", headline_key: "signals.baseline.above", value: { estimate: 66, low: 54, high: 60, unit: "bpm", per: null } }),
      sig({ id: "water_14d", state: "not_enough_data", headline_key: "signals.nodata", value: null,
        missing: [{ key: "signals.missing.days", need: 11, have: 9 }], replay: true,
        inputs: [{ ...sig().inputs[0], ind: "intake_water_ml", src: "replay", dev: "catalog" }] }),
    ] };
    renderSignalsBody(root, body, [], NOW);
    const t = root.textContent ?? "";
    expect(t).toContain("Body");
    expect(t).toContain("Food and body mass");
    expect(t).toContain("Above your own usual range: 66.0 bpm");
    expect(t).toContain("Needs 11 days with a value; has 9.");
    expect(t).toContain("Replay (recorded) · catalog");
    expect(t).toContain("This is not a diagnosis.");
    expect(root.querySelector('[data-signal="water_14d"]')?.classList.contains("greyed")).toBe(true);
    expect(root.querySelector('[data-signal="rest_hr_baseline"]')?.classList.contains("watch")).toBe(true);
    const replayChip = [...root.querySelectorAll('[data-signal="water_14d"] .chip')].find((c) => c.textContent?.startsWith("Replay"))!;
    expect(replayChip.classList.contains("replay")).toBe(true);
    expect(replayChip.classList.contains("estimate")).toBe(false);
  });

  test("card parts: sparkline, window, input age, self-check, method with alpha and limits", () => {
    const root = document.createElement("div");
    const trend = sig({ id: "cabin_temp_6h", crew: null, kind: "trend", headline_key: "signals.trend.up",
      value: { estimate: 0.5, low: 0.31, high: 0.72, unit: "C", per: "h" },
      method: { ...sig().method, name: "theil_sen", ref: "Sen 1968", alpha: 0.05 },
      limits: ["signals.limit.benchSensor", "signals.limit.independence"],
      inputs: [{ ...sig().inputs[0], ind: "cabin_temp", dev: "DHT11", node: "cabin-1" }] });
    const flat = sig({ id: "sleep_baseline", series: [["2026-11-20T10:00:00.000Z", 7]] });
    renderSignalsBody(root, { crew: null, at: "x", signals: [sig(), trend, flat] },
      [prompt({ kind: "signal_body" })], NOW);
    const hr = root.querySelector<HTMLElement>('[data-signal="rest_hr_baseline"]')!;
    expect(hr.querySelector(".spark polyline")).not.toBeNull();
    expect(hr.textContent).toContain("14 points, 2026-11-06T10:00 to 2026-11-20T10:00");
    expect(hr.textContent).toContain("Hobby sensor · Ring (delayed cloud sync) · 1 h ago");
    expect(hr.textContent).not.toContain("· RING ·");
    expect(hr.textContent).toContain("A self-check is open for this signal.");
    expect(root.querySelector('[data-signal="sleep_baseline"] .spark')).toBeNull();
    expect(root.querySelector('[data-signal="sleep_baseline"]')!.textContent).not.toContain("A self-check is open");

    const how = root.querySelector<HTMLDetailsElement>('[data-signal="cabin_temp_6h"] details')!;
    how.open = true;
    const ht = how.textContent ?? "";
    expect(ht).toContain("theil_sen · Sen 1968");
    expect(ht).toContain("α = 0.05");
    expect(ht).toContain("14 points, 2026-11-06T10:00 to 2026-11-20T10:00");
    expect(ht).toContain("Bench hobby sensor, not a certified device.");
    expect(ht).toContain("Assumes independent points.");
    expect(root.querySelector('[data-signal="rest_hr_baseline"] details')!.textContent).not.toContain("α");
    const badge = [...root.querySelectorAll('[data-signal="cabin_temp_6h"] .chip')].map((c) => c.textContent);
    expect(badge).toContain("DHT11 reads ±2 °C");
  });

  test("camera input chips carry the camera label and the estimate badge", () => {
    const root = document.createElement("div");
    renderSignalsBody(root, { crew: "crew-a", at: "x", signals: [sig({ id: "lift_work_sets", kind: "trend",
      inputs: [{ ...sig().inputs[0], ind: "rep_work_j", src: "hobby", dev: "camera" }] })] }, [], NOW);
    const chips = [...root.querySelectorAll(".chip")];
    expect(chips.map((c) => c.textContent)).toEqual(["Hobby sensor · Camera · 1 h ago", "Estimate"]);
    expect(chips[1].classList.contains("estimate")).toBe(true);
  });

  test("per-crew cards name their crew and mark replay", () => {
    const root = document.createElement("div");
    renderSignalsBody(root, { crew: null, at: "x", signals: [
      sig({ crew: "crew-a", replay: true }), sig({ crew: "crew-b" }), sig({ crew: "crew-c", replay: true }),
      sig({ id: "cabin_temp_6h", crew: null }),
    ] }, [], NOW);
    const card = (c: string) => root.querySelector<HTMLElement>(`[data-signal="rest_hr_baseline"][data-crew="${c}"] .who`)!;
    expect(card("crew-a").textContent).toBe("Crew A · Replay (recorded)");
    expect(card("crew-b").textContent).toBe("Crew B");
    expect(card("crew-c").textContent).toBe("Crew C · Replay (recorded)");
    expect(root.querySelector('[data-signal="cabin_temp_6h"] .who')).toBeNull();
  });

  test("lagged pairs show their side-by-side table, one row per pair, empty cells left empty", () => {
    const root = document.createElement("div");
    const daily = sig({ id: "training_vs_rest_hr", kind: "lagged_pair", headline_key: "signals.pair.few", value: null,
      method: { ...sig().method, n: 3 },
      pairs: [["2026-11-17", 320.2, 55], ["2026-11-18", 0, 56.5], ["2026-11-19", 210, null as unknown as number]] });
    renderSignalsBody(root, { crew: "crew-a", at: "x", signals: [daily, cabinPair(), sig()] }, [], NOW);
    const rows = [...root.querySelectorAll('[data-signal="training_vs_rest_hr"] table.pairs tbody tr')];
    expect(rows).toHaveLength(3);
    expect([...rows[0].querySelectorAll("td")].map((c) => c.textContent)).toEqual(["2026-11-17", "320.2", "55.0"]);
    expect([...rows[1].querySelectorAll("td")].map((c) => c.textContent)).toEqual(["2026-11-18", "0.00", "56.5"]);
    expect([...rows[2].querySelectorAll("td")].map((c) => c.textContent)).toEqual(["2026-11-19", "210.0", ""]);
    const head = root.querySelector('[data-signal="training_vs_rest_hr"] table.pairs thead')!.textContent;
    expect(head).toContain("Training work (kg·m)");
    const cab = [...root.querySelectorAll('[data-signal="cabin_vs_earth"] table.pairs tbody tr')];
    expect(cab).toHaveLength(2);
    expect([...cab[1].querySelectorAll("td")].map((c) => c.textContent)).toEqual(["2026-11-20T07:00", "11.9", "21.7", "1"]);
    expect(root.querySelector('[data-signal="cabin_vs_earth"] table.pairs thead')!.textContent).toContain("Lag (h)");
    expect(root.querySelector('[data-signal="rest_hr_baseline"] table.pairs')).toBeNull();
    const cabText = root.querySelector('[data-signal="cabin_vs_earth"]')!.textContent ?? "";
    expect(cabText).not.toContain("{");
    expect(cabText).toContain("64 points,");
  });

  test("signals off on the hub", () => {
    const root = document.createElement("div");
    renderSignalsBody(root, null, [], NOW);
    expect(root.textContent).toContain("the signals feature is off");
  });

  test("the outdoor data credit is on the cabin_vs_earth card only", () => {
    const root = document.createElement("div");
    const pair = cabinPair({ headline_key: "signals.pair.few", detail: { lags: [] }, pairs: [] });
    const body: SignalsBody = { crew: null, at: "x", signals: [
      pair, sig(), sig({ id: "cabin_temp_6h", crew: null, kind: "trend", limits: ["signals.limit.benchSensor"] }),
    ] };
    renderSignalsBody(root, body, [], NOW);
    const credit = "Weather data by Open-Meteo.com (CC BY 4.0)";
    const cards = [...root.querySelectorAll<HTMLElement>("[data-signal]")];
    expect(cards.length).toBe(3);
    for (const c of cards) {
      expect(c.textContent?.includes(credit), c.dataset.signal).toBe(c.dataset.signal === "cabin_vs_earth");
    }
    expect((root.textContent ?? "").split(credit).length - 1).toBe(1);
    expect(root.querySelector('[data-signal="cabin_vs_earth"] a')).toBeNull();
  });
});

describe("signals screen loader", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    setCurrentCrew(null);
  });

  const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

  function stub(signals: () => Response | Promise<Response>) {
    const calls: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (u: string) => {
      calls.push(u);
      return u.startsWith("/api/prompts") ? json([]) : signals();
    }));
    return calls;
  }

  test("a 503 signals_off or a 404 says the feature is off", async () => {
    for (const r of [() => json({ reason: "signals_off" }, 503), () => json({ detail: "Not Found" }, 404)]) {
      stub(r);
      const root = document.createElement("div");
      const dispose = renderSignals(root);
      await vi.waitFor(() => expect(root.textContent).toContain("the signals feature is off"));
      dispose();
    }
  });

  test("any other failure says the signals could not be loaded, never that the feature is off", async () => {
    const fails: (() => Response | Promise<Response>)[] = [
      () => json({ reason: "boom" }, 500), () => json({ reason: "bad_crew" }, 422), () => json({ reason: "busy" }, 503),
      () => Promise.reject(new TypeError("network down")),
    ];
    for (const r of fails) {
      stub(r);
      const root = document.createElement("div");
      const dispose = renderSignals(root);
      await vi.waitFor(() => expect(root.textContent).toContain("Signals could not be loaded; retrying."));
      expect(root.textContent).not.toContain("feature is off");
      dispose();
    }
  });

  test("a failed refresh keeps the last cards; dispose stops the timer and the crew listener", async () => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
    let fail = false;
    const calls = stub(() => (fail ? json({ reason: "boom" }, 500) : json({ crew: null, at: "x", signals: [sig()] })));
    const root = document.createElement("div");
    const dispose = renderSignals(root);
    await vi.waitFor(() => expect(root.querySelector('[data-signal="rest_hr_baseline"]')).not.toBeNull());
    fail = true;
    vi.advanceTimersByTime(30_000);
    await vi.waitFor(() => expect(root.textContent).toContain("Signals could not be loaded; retrying."));
    expect(root.querySelector('[data-signal="rest_hr_baseline"]')).not.toBeNull();
    dispose();
    const n = calls.length;
    vi.advanceTimersByTime(120_000);
    setCurrentCrew("crew-b");
    await Promise.resolve();
    expect(calls.length).toBe(n);
  });
});

describe("panel top bar signals chip", () => {
  test("shows the real notable count live, with replay counted apart", () => {
    const live = topBar({ replay: false, now: () => NOW });
    live.update({ status: null, sessions: null, weather: null, link: null });
    expect(live.node.textContent).not.toContain("Signals");
    live.signals({ crew: null, at: "x", signals: [sig({ state: "notable" })] });
    expect(live.node.textContent).toContain("Signals 1 notable");
    expect(live.node.querySelector('a[href="#/signals"]')).not.toBeNull();
    expect(live.node.querySelector('a[href="#/signals"] .dot')!.classList.contains("watch")).toBe(true);
    live.signals({ crew: null, at: "x", signals: [sig({ state: "notable" }), sig({ state: "notable", replay: true, crew: "crew-c" })] });
    expect(live.node.textContent).toContain("Signals 1 notable, 1 in replay");
    live.signals({ crew: null, at: "x", signals: [sig({ state: "notable", replay: true })] });
    expect(live.node.textContent).toContain("Signals 0 notable, 1 in replay");
    expect(live.node.querySelector('a[href="#/signals"] .dot')!.classList.contains("watch")).toBe(false);
    // A later update of the other chips keeps the signals chip.
    live.update({ status: null, sessions: null, weather: null, link: null });
    expect(live.node.textContent).toContain("Signals 0 notable, 1 in replay");
    live.dispose();
  });

  test("a failed request shows no data, never 0 notable", () => {
    const live = topBar({ replay: false, now: () => NOW });
    live.update({ status: null, sessions: null, weather: null, link: null });
    live.signals(null);
    const chip = live.node.querySelector('a[href="#/signals"]')!;
    expect(chip.textContent).toContain("Signals No data");
    expect(chip.textContent).not.toContain("notable");
    expect(chip.querySelector(".dot")!.classList.contains("watch")).toBe(false);
    live.dispose();
  });
});

describe("panel signals request", () => {
  afterEach(() => vi.useRealTimers());

  test("the panel cards never wait on signals, and signals refetch every 30 s, not every tick", async () => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval", "Date"] });
    vi.setSystemTime(NOW);
    let resolve: (b: SignalsBody) => void = () => {};
    const signals = vi.fn(() => new Promise<SignalsBody>((r) => {
      resolve = r;
    }));
    const no = () => Promise.reject(new Error("not in this test"));
    const src: PanelSource = {
      replay: false, now: () => Date.now(),
      status: () => Promise.resolve({ results: [], nodes: [] } as never),
      sessions: () => Promise.resolve([]), reps: no, readings: no, foodDay: no, exerciseDay: no, spaceWeather: no,
      issCabin: no, issReference: no, link: no, signals,
    };
    const root = document.createElement("div");
    const dispose = renderPanel(root, src);
    await vi.waitFor(() => expect(root.querySelector(".p-top")!.textContent).toContain("Cabin sensors"));
    expect(root.querySelector(".p-top")!.textContent).not.toContain("Signals");
    resolve({ crew: null, at: "x", signals: [sig({ state: "notable" })] });
    await vi.waitFor(() => expect(root.querySelector(".p-top")!.textContent).toContain("Signals 1 notable"));
    expect(signals).toHaveBeenCalledTimes(1);
    vi.advanceTimersByTime(10_000);
    vi.advanceTimersByTime(10_000);
    await Promise.resolve();
    expect(signals).toHaveBeenCalledTimes(1);
    vi.advanceTimersByTime(10_000);
    await vi.waitFor(() => expect(signals).toHaveBeenCalledTimes(2));
    dispose();
  });
});

describe("hub keys from slice 4 (D45 integration)", () => {
  test("a pair with no spread on one side says so, at one lag or several", () => {
    const flat = sig({ id: "last_meal_vs_sleep", kind: "lagged_pair", value: null, headline_key: "signals.pair.noSpread",
      method: { ...sig().method, n: 22 } });
    expect(headline(flat)).toBe("Side by side: 22 pairs, but one side never changes, so there is nothing to rank.");
    const lagged = sig({ id: "cabin_vs_earth", kind: "lagged_pair", crew: null, value: null, headline_key: "signals.pair.noSpread",
      detail: { lags: [{ lag_h: 0, n: 30, rho: null, low: null, high: null, key: "signals.pair.lagNoSpread" },
        { lag_h: 1, n: 5, rho: null, low: null, high: null, key: "signals.pair.lagFew" }] } });
    expect(headline(lagged)).toContain("Side by side at 0 to 1 h lags");
    expect(lagLines(lagged)).toEqual([
      "0 h later: 30 pairs, but one side never changes.",
      "1 h later: 5 pairs, too few to say anything.",
    ]);
  });

  test("a weekly slope reads per week", () => {
    const mass = sig({ id: "body_mass_30d", kind: "trend", headline_key: "signals.trend.down",
      value: { estimate: -0.35, low: -0.5, high: -0.2, unit: "kg", per: "week" } });
    expect(headline(mass)).toBe("Trend down: −0.35 kg per week (interval −0.50 to −0.20).");
  });
});
