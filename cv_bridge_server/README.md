# Smart Helmet CV Bridge Server

This mini service wraps the existing `localization/CV` module for the mobile app.
It is intentionally optional: if Google Street View, the model files, or the
server itself are unavailable, the Android app keeps using DR and shows Vision
as unavailable instead of failing.

## Install

From the repo root:

```powershell
pip install -r cv_bridge_server\requirements.txt
pip install -r localization\CV\requirements.txt
```

The existing CV model weights should be here:

```text
localization/CV/models/best.pth
localization/CV/models/scene_classifier.pth
```

Only `best.pth` is required. The scene classifier is optional.

## Google Street View

Set one of these environment variables:

```powershell
$env:GOOGLE_STREET_VIEW_API_KEY="your_google_maps_key"
# or
$env:GOOGLE_MAPS_API_KEY="your_google_maps_key"
```

For a local demo without Google imagery, you can allow the static fallback image:

```powershell
$env:CV_SERVER_ALLOW_STATIC_FALLBACK="1"
```

The static fallback reports `DEGRADED`, not `OK`, so the app knows Vision is not
running as intended.

## Run

```powershell
python -m uvicorn cv_bridge_server.main:app --host 0.0.0.0 --port 8010
```

Health check:

```powershell
curl http://localhost:8010/health
```

For a physical phone, make sure the phone and laptop are on the same Wi-Fi and
set the Android app's `VISION_SERVER_URLS` in
`mobile_new/src/services/visionService.ts` to your laptop IP, for example:

```ts
'http://192.168.1.5:8010'
```

## Mobile Flow

When GPS is available, the app does not call this server. When GPS becomes stale
or disabled, NCS sends:

- session id
- origin and destination coordinates
- current route-projected coordinates
- route polyline
- DR distance and route progress

The server returns:

- `OK` plus a visual event and optional position hint when CV is working
- `DEGRADED` when it is using fallback imagery or partial CV
- `UNAVAILABLE` when Google/model/server pieces are missing

NCS fuses the response with DR only if it is healthy enough. Otherwise it keeps
DR active and shows the Vision status in the fallback panel.
