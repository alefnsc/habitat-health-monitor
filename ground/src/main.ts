import "./style.css";
import { apiBase } from "./paths";
import { emptyView, reduce } from "./model";
import { render } from "./render";
import { liveSource } from "./sources";
import type { GroundView } from "./types";

const root = document.querySelector<HTMLDivElement>("#app")!;

let view: GroundView = emptyView();

function startLive(): void {
  const base = apiBase("live", import.meta.env.VITE_API_BASE as string | undefined);
  liveSource(
    base,
    (a) => {
      view = reduce(view, a, Date.now());
    },
    (...args) => fetch(...args),
  );
  const draw = () => render(root, view, Date.now(), null);
  draw();
  setInterval(draw, 500);
}

startLive();
