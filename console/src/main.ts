import "./styles.css";
import "uplot/dist/uPlot.min.css";

export const SCREENS = ["status", "entry", "history", "exercise", "nasa", "prompts", "body"] as const;
export type Screen = (typeof SCREENS)[number];

export function screenFromHash(hash: string): Screen {
  const name = hash.replace(/^#\/?/, "");
  return (SCREENS as readonly string[]).includes(name) ? (name as Screen) : "status";
}

const TITLES: Record<Screen, string> = {
  status: "Status board",
  entry: "Manual entry",
  history: "History",
  exercise: "Exercise",
  nasa: "NASA panel",
  prompts: "Prompts",
  body: "Body figure",
};

export function mountApp(root: HTMLElement): void {
  root.innerHTML = `
    <div class="banner">Educational prototype, not a medical device.</div>
    <header class="top">
      <nav class="nav"></nav>
    </header>
    <main><h1 class="screen-title"></h1><section id="screen"></section></main>`;
  const nav = root.querySelector("nav")!;
  const title = root.querySelector("h1")!;
  for (const s of SCREENS) {
    const b = document.createElement("button");
    b.textContent = TITLES[s];
    b.dataset.screen = s;
    b.addEventListener("click", () => {
      location.hash = `#/${s}`;
    });
    nav.appendChild(b);
  }
  const render = () => {
    const cur = screenFromHash(location.hash);
    title.textContent = TITLES[cur];
    nav.querySelectorAll("button").forEach((b) => {
      if ((b as HTMLElement).dataset.screen === cur) b.setAttribute("aria-current", "page");
      else b.removeAttribute("aria-current");
    });
  };
  window.addEventListener("hashchange", render);
  render();
}

const appRoot = typeof document !== "undefined" ? document.getElementById("app") : null;
if (appRoot) mountApp(appRoot);
