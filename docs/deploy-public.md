# Public ground segment: setup (team owner)

Run every command from the repository root with the virtualenv active (`. .venv/bin/activate`).

1. Claim the free domain from the Space Apps Global Offer (the registry's partner registrar). Write the domain in `docs/decisions/links.md` once it resolves.
2. Create a hosting project from this repository on the free plan. The repository root is the project root; `vercel.json` sets the build, output and routing.
3. Add the Redis integration to the project (free plan). It must provide the REST URL and token as environment variables: `UPSTASH_REDIS_REST_URL` and `UPSTASH_REDIS_REST_TOKEN` (the names `KV_REST_API_URL` and `KV_REST_API_TOKEN` are also accepted). Check they appear in the project's environment variables.
4. Generate a secret: `python -c "import secrets; print(secrets.token_urlsafe(32))"`. Set it as `GROUND_INGEST_SECRET` in the hosting project and export it in the habitat shell or `.env`. Never paste it in chat or commit it.
5. Add the domain to the hosting project and set the DNS records the hosting project shows, at the registrar.
6. Deploy. Check `https://<domain>/ground/summary` returns JSON and `https://<domain>/` shows the replay (no habitat running yet).
7. Smoke from the habitat with synthetic data only (`PUBLIC_CREWS` empty), with `GROUND_INGEST_SECRET` exported. The hub must already be running on port 8000: start it with `python -m hub` (default port, or `python -m hub --port 8000`). Run linksim and hub.sim in two separate terminals. Pass `--ground ""` so linksim has no local receiver (empty means none; otherwise it expects the local receiver on port 8100 and keeps retrying it):
   `PUBLIC_GROUND_URL=https://<domain> python -m linksim --config linksim/link.demo.json --ground ""`
   (`PUBLIC_GROUND_URL` is equivalent to the `--public-ground https://<domain>` flag) while
   `python -m hub.sim --http http://127.0.0.1:8000 --file data/replay/l0-synthetic.jsonl --speed 10` feeds the hub.
   Within a minute the page switches to live and shows cabin data and sim-1 crew data only.
8. Never replay recordings of real people through node sim-1 while PUBLIC_GROUND_URL is set: sim-1 items are always published as synthetic. While sim-1 runs with the public uplink on, do not list in `PUBLIC_CREWS` a crew id that sim-1 also uses: `data/replay/l0-synthetic.jsonl` carries `crew-a`, so keep `crew-a` out of `PUBLIC_CREWS` during that time.
9. Collect signed consent forms (`docs/consent.md`) before adding any crew id to `PUBLIC_CREWS`. Never add a minor. Keep `PUBLIC_REPS=0` whenever anyone under 18 uses the rig. A body node assigned to a public crew id publishes whoever wears it, so check who wears it before a session.
10. Withdrawal. linksim reads `PUBLIC_CREWS` only from its own environment or the `--public-crews` flag, so editing `.env` or the hosting project changes nothing for a running linksim.
   1. Stop linksim.
   2. Run the signed purge:
   `python -c "import json,httpx,os; from receiver.signing import sign; b=json.dumps({'crew':'crew-a'}).encode(); print(httpx.post(os.environ['PUBLIC_GROUND_URL']+'/ground/purge', content=b, headers={'X-Habitat-Signature': sign(b, os.environ['GROUND_INGEST_SECRET'])}).json())"`
   with `PUBLIC_GROUND_URL` and `GROUND_INGEST_SECRET` exported. It prints `{'removed': N}`. A reply with a `detail` message means the secret or the crew id is wrong. Purge removes only the public copy; readings on the habitat hub stay local. Cached copies may stay visible for about a minute.
   3. Start linksim again with an explicit `--public-crews "<list without the withdrawn id>"` (or re-source `.env` first, after removing the id there).
   4. Check the startup line it prints, `public crews: ...; reps public: ...`, and confirm the withdrawn id is not in the set.
11. When the habitat runs offline, unset `PUBLIC_GROUND_URL` so linksim does not try the public uplink.
12. Each ingest costs about 5 Redis commands. Before a long run, check the free-plan daily command limit in the Redis dashboard and compare it with the expected number of flushes (one every `PUBLIC_FLUSH_S` seconds, 10 by default).
