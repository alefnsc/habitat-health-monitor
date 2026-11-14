# Live ground segment on a public domain — design (D38)

Status: approved by the team owner, 2026-11-14 ~12:10 (UTC−03:00), section by section.

## 1. Goal

Give the judged public link a live "Earth" side. While the habitat runs, the data that crosses the simulated Mars link appears on a public page on the team's own domain, after the light-time delay. When the habitat is off, the same page plays the labelled replay. The habitat hub itself stays offline (LAN only), as the spec requires.

## 2. Constraints

| ID | Constraint | Consequence |
|---|---|---|
| R2 | The final-project link is public, with no login | The page and the read API need no account |
| R5 | No company name or logo, and no promotion | The page and repo name no hosting or domain provider. The domain comes from the Space Apps Global Offer (free domain through the registry's partner registrar) |
| R8 | No likeness of anyone under 18 | Recordings, photos and video show adult team members only. Readings of anyone under 18 are never published, whatever the consent |
| Consent | Real people's health data is published only with that person's documented consent | Body data reaches the public side only for crew ids listed in `PUBLIC_CREWS` (§5) |
| Privacy | Health data is sensitive personal data | Public storage keeps at most 48 h. A signed purge removes a crew's data on request |
| Offline hub | The habitat must work with no link to Earth | The cloud is a second, optional destination. The habitat never depends on it |

## 3. Architecture

```
hub outbox ──> link simulator ──(light-time hold, blackouts)──┬──> local ground receiver (everything; team-only)
                                                               └──> consent filter ──HMAC──> public ground segment
                                                                                                (static page + ingest/read API + Redis)
```

- The link simulator keeps **one cursor per destination**, so a slow or failing public destination never blocks the local one.
- The public ground segment is one hosting project built from the repository. It has:
  - the static ground page at `/`;
  - the console replay at `/console/`;
  - one Python ASGI function serving `/ground/*`.

## 4. Components and interfaces

### 4.1 Consent filter (`linksim/consent.py`)

`filter_items(items: list[OutboxItem], public_crews: frozenset[str]) -> list[OutboxItem]`

- **Always passed:**
  - `reading` items whose indicator is in `CABIN_INDS`, or is `space_weather` or `rad_dose_cum`;
  - every item whose node is `sim-1` (synthetic crew);
  - link and alert items about cabin or NASA rules.
- **Passed only when the item's crew is in `public_crews`:**
  - `reading` items whose indicator is in `BODY_INDS | INTAKE_INDS`;
  - `prompt_answer` items;
  - `alert` items on body or intake rules.
- **Reps** (`rep` items) carry no crew, so they pass only when `PUBLIC_REPS=1`. The default is off.
- **Always dropped:** anything else.
- Dropped items still advance the public cursor, so nothing is retried and nothing leaks later.

`PUBLIC_CREWS` is a comma list in the habitat's `.env`, empty by default. Only crew ids of adults with a signed consent form go in it.

### 4.2 Signed delivery (link simulator)

- **New setting `PUBLIC_GROUND_URL`.** When it is empty, there is no public destination, and today's behaviour is unchanged.
- **Signing.** Each `POST {PUBLIC_GROUND_URL}/ground/ingest` carries the header `X-Habitat-Signature: sha256=<hex HMAC-SHA256 of the exact body bytes>`. The key is `GROUND_INGEST_SECRET`.
- **Same body as the local receiver:** `{beacon, items[]}`.
- **Failures** raise `LinkDown` for that destination only.

### 4.3 Public ground API (`api/ground/index.py`, ASGI)

`vercel.json` rewrites `/ground/(.*)` to the function, so the paths match the local receiver exactly.

| Method + path | Behaviour |
|---|---|
| `POST /ground/ingest` | Requires a valid signature (401 otherwise). Idempotent by outbox `id`. Returns `{max_id}` like the local receiver. Body limit 1 MB, at most 1000 items per call |
| `GET /ground/arrivals?after=&limit=` | Same response shape as the local receiver. `limit` ≤ 1000 |
| `GET /ground/summary` | Same shape as the local receiver, plus `last_arrival_at` |
| `POST /ground/purge` | Signed. Body `{crew}` deletes every stored item of that crew and returns a count |

**Storage:** a `RedisStore` implements the local receiver's store interface. It holds items in a sorted set keyed by outbox id, plus a hash per item. Its limits are a cap of 20,000 items (oldest trimmed first) and a 48 h expiry on every key.

**Client:** the Upstash REST client (`upstash-redis`, MIT). Its URL and token arrive as environment variables from the hosting integration and are never in the repository.

**Dependencies:** `api/requirements.txt` lists only the function's dependencies, because the hosting Python builder installs from that file. It is a recorded exception to D15 (one root `pyproject.toml`). A test keeps it in sync with the `cloud` extra in `pyproject.toml`.

### 4.4 Ground page live mode

- The build flag `VITE_GROUND_API` sets where the page reads from:
  - `""` reads the page's own origin (public deployment);
  - unset means replay only (today's GitHub Pages build).
- **Mode switching:**
  - The page starts live.
  - With no arrival for 5 minutes (from `summary.last_arrival_at`), or on any read error, it shows the replay with the existing notice.
  - It returns to live when arrivals resume.
- The page always shows the replay or synthetic banner whenever the data shown is not live. Live data from `sim-1` carries a "synthetic crew" label.

### 4.5 Consent form (`docs/consent.md`)

- English and Portuguese.
- Covers what is collected, what may go public (crew id only, never a name), the 48 h public retention, how to withdraw (purge), and the right to refuse with no effect on taking part.
- Has a guardian line for minors, plus the team rule that minors' readings are never published.
- Signed copies stay off the repository.

## 5. Failure modes

| Case | Behaviour |
|---|---|
| Public destination down or slow | Its cursor waits and retries. The local destination and the habitat are unaffected |
| Wrong or missing signature | 401, and nothing is stored |
| Duplicate batch | Stored once, by outbox id |
| Redis full or expired | Oldest items are trimmed or expire. The page falls back to the replay when there is nothing recent |
| Consent withdrawn | The team owner removes the crew from `PUBLIC_CREWS` and calls the signed purge |
| Habitat off | After 5 minutes the page shows the replay |

## 6. Testing

- **Unit tests:**
  - consent filter: every item kind, sim-1, the reps flag, and the empty list;
  - HMAC signing and verification: valid, tampered body, missing header, wrong key;
  - `RedisStore` against an in-memory fake: idempotency, cap, purge;
  - the `requirements.txt` sync test.
- **End-to-end, in-process:** link engine → consent filter → signed POST → ASGI app with the fake store → `GET /ground/arrivals`. Body items of a non-listed crew never appear; cabin and `sim-1` items do.
- **Ground page:** vitest for the live/replay switch, using a fake fetch.
- **After the team owner sets up the hosting:**
  - a smoke run from the habitat (`sim-1` only, `PUBLIC_CREWS` empty);
  - then a private-window check that the page shows live data and no body data of real people.

## 7. Rollout and ownership

1. **Agents (repository):** §4.1–4.5, `vercel.json`, build settings, tests, and documentation in `docs/deploy-public.md`, which covers the setup steps without naming any provider in UI text.
2. **Team owner (accounts and DNS):**
   - claim the free domain from the Global Offer;
   - create the hosting project from the repository (free plan);
   - add the Redis integration;
   - set `GROUND_INGEST_SECRET` in the hosting project and in the habitat `.env`;
   - add the domain and set DNS at the registrar;
   - collect consent forms.
3. **After the domain is live:**
   - D24 and `docs/decisions/links.md` change so that the judged link is the domain;
   - the GitHub Pages site stays as a mirror;
   - the project page uses the domain.
4. **R8 throughout:** D31 (OBS build scenes) records only adult team members, and only the hands and bench of the team owner.
