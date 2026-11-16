# One image for the hub, the link simulator and the ground receiver (D47).
# Build from a clean clone: docker build -t habitat-health-monitor:local .
# compose.yaml picks the process: python -m hub (default), python -m linksim, python -m receiver
# or python -m hub.sim. No secret, no .env, no var/ and no broker password file goes into the image.

# The console and camera pages are static files, the same on every CPU, so this stage runs on the
# build machine's own platform even when the image is built for linux/arm64.
FROM --platform=$BUILDPLATFORM node:22-slim AS web
WORKDIR /src
COPY console/package.json console/package-lock.json console/
COPY camera/package.json camera/package-lock.json camera/
RUN npm --prefix console ci --no-audit --no-fund \
 && npm --prefix camera ci --no-audit --no-fund
# The console reads data/thresholds.json and data/guidance.json at build time; the camera page
# imports the vendored ground-truth packages.
COPY data/ data/
COPY vendor/ vendor/
COPY console/ console/
COPY camera/ camera/
# No network: the camera prebuild copies the pinned wasm from node_modules and checks the committed
# pose model's SHA-256, and neither build may fetch anything.
RUN --network=none npm --prefix console run build \
 && npm --prefix camera run build

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore
# The Python packages (hub*, linksim*, receiver*, nodes*) go to site-packages; the sources stay out
# of the image's layers.
RUN --mount=type=bind,target=/src,rw pip install --no-cache-dir /src
RUN useradd --uid 1000 --user-group --home-dir /app --no-create-home --shell /usr/sbin/nologin habitat
WORKDIR /app
COPY data/ data/
COPY linksim/*.json linksim/
COPY --from=web /src/console/dist console/dist
COPY --from=web /src/camera/dist camera/dist
RUN mkdir var && chown habitat:habitat var
ENV HUB_CONSOLE_DIST=/app/console/dist \
    HUB_CAMERA_DIST=/app/camera/dist \
    HUB_DB=/app/var/hub.db
USER habitat
VOLUME ["/app/var"]
EXPOSE 8000 8100 8200
# The hub's own check. compose.yaml gives the link simulator and the receiver theirs.
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/status', timeout=4)"]
CMD ["python", "-m", "hub"]
