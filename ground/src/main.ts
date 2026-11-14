import "./style.css";
import { replayUrl } from "./paths";

const app = document.querySelector<HTMLDivElement>("#app")!;

app.innerHTML = `
  <main>
    <h1>Ground segment — Earth's view</h1>
    <p class="notice" role="note">
      This page shows synthetic or replay data until real data exists.
      Educational prototype, not a medical device.
    </p>
    <p id="status" aria-live="polite">Loading…</p>
  </main>
`;

const status = document.querySelector<HTMLParagraphElement>("#status")!;

async function load(): Promise<void> {
  try {
    const res = await fetch(replayUrl(import.meta.env.BASE_URL));
    if (!res.ok) {
      status.textContent = "Replay data not yet published";
      return;
    }
    await res.json();
    status.textContent = "Replay data loaded";
  } catch {
    status.textContent = "Replay data not yet published";
  }
}

void load();
