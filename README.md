# myra
Android App MonoRepo for listening songs for free in car with AI voice assist

## JioSaavn proxy API

`api/jiosaavn.py` is a single reverse-proxy endpoint over the (undocumented)
JioSaavn web API. It uses a `curl_cffi` session that impersonates a real
browser's TLS fingerprint, so it isn't blocked the way plain `requests`
traffic to JioSaavn is.

```
GET  /api/jiosaavn_route?type=<type>&query=<query>   # search | autocomplete | song
POST /api/jiosaavn_route   {"query": "<encrypted_media_url>"}  # audio
```

`audio` is POST-only: `encrypted_media_url` contains characters (`+`, `/`)
that get corrupted when passed unescaped in a query string, so it goes in
a JSON body instead.

| Param   | Required | Applies to                | Description                                                  |
|---------|----------|----------------------------|----------------------------------------------------------------|
| `type`  | yes      | GET requests only          | One of `search`, `autocomplete`, `song`.                        |
| `query` | yes      | GET (querystring) / POST (JSON body) | Meaning depends on `type` — see table below.         |

| `type`         | `query` means               |
|----------------|------------------------------|
| `search`       | free-text search string      |
| `autocomplete` | free-text search string      |
| `song`         | a song id/token (from a `perma_url`, e.g. `.../song/let-me-love-you/GlADRz50Z0A` → `GlADRz50Z0A`) |
| `audio`        | an `encrypted_media_url` (from a `search`/`song` result), sent via `POST` body |

Response envelope (200):

```json
{
  "type": "search",
  "query": "Let me love you",
  "data": [ /* shape depends on type, see below */ ]
}
```

Errors: `400` (missing/invalid `type` or `query`) or `502` (upstream
JioSaavn call failed), both shaped `{ "error": "..." }`.

---

### `type=search`

```
GET /api/jiosaavn_route?type=search&query=Let%20me%20love%20you
```

`data` is a list of songs:

```json
[
  {
    "encrypted_media_url": "ID2ieOjCrwfgWvL5sXl4B1ImC5QfbsDybn6+1ArlR65DXyfmERgXytmFmYCqu6vdEDPyJ6nqm+l87Pb/ExKuGhw7tS9a8Gtq",
    "key": "j8hvJDPs",
    "title": "Let Me Love You",
    "subtitle": "DJ Snake ft. Justin Bieber - Encore",
    "perma_url": "https://www.jiosaavn.com/song/let-me-love-you/GlADRz50Z0A",
    "image": "https://c.saavncdn.com/273/Encore-English-2016-20190419221937-150x150.jpg",
    "language": "english",
    "year": "2016",
    "play_count": "138665528",
    "more_info": {
      "album": "Encore",
      "label": "DJ Snake Def Jam",
      "album_url": "https://www.jiosaavn.com/album/encore/4iGw272FXHY_",
      "duration": "205"
    }
  }
]
```

---

### `type=autocomplete`

```
GET /api/jiosaavn_route?type=autocomplete&query=paraayuva
```

`data` is a list of lightweight suggestions (useful for a search-as-you-type box):

```json
[
  {
    "id": "j8hvJDPs",
    "title": "Let Me Love You",
    "subtitle": "Encore",
    "type": "song",
    "image": "https://c.saavncdn.com/273/Encore-English-2016-20190419221937-150x150.jpg",
    "perma_url": "https://www.jiosaavn.com/song/let-me-love-you/GlADRz50Z0A",
    "more_info": {
      "album": "Encore",
      "album_id": "2502208",
      "ctr": 24,
      "score": "3286295.2",
      "vcode": "010912291156078",
      "vlink": "https://jiotunepreview.jio.com/content/Converted/010912291112421.mp3",
      "primary_artists": "DJ Snake",
      "singers": "",
      "video_available": null,
      "triller_available": false,
      "language": "english"
    },
    "explicit_content": "0",
    "mini_obj": true,
    "description": "DJ Snake · Encore"
  }
]
```

To go from a `perma_url` to the `song_id` needed for `type=song`, take the
last path segment: `.../song/let-me-love-you/GlADRz50Z0A` → `GlADRz50Z0A`.

---

### `type=song`

```
GET /api/jiosaavn_route?type=song&query=By45YAV6Unk
```

`data` is a list with the full song details (same shape as a `search` result):

```json
[
  {
    "encrypted_media_url": "ID2ieOjCrwfgWvL5sXl4B1ImC5QfbsDybn6+1ArlR65DXyfmERgXytmFmYCqu6vdEDPyJ6nqm+l87Pb/ExKuGhw7tS9a8Gtq",
    "key": "j8hvJDPs",
    "title": "Let Me Love You",
    "subtitle": "DJ Snake ft. Justin Bieber - Encore",
    "perma_url": "https://www.jiosaavn.com/song/let-me-love-you/GlADRz50Z0A",
    "image": "https://c.saavncdn.com/273/Encore-English-2016-20190419221937-150x150.jpg",
    "language": "english",
    "year": "2016",
    "play_count": "138665528",
    "more_info": {
      "album": "Encore",
      "label": "DJ Snake Def Jam",
      "album_url": "https://www.jiosaavn.com/album/encore/4iGw272FXHY_",
      "duration": "205"
    }
  }
]
```

`encrypted_media_url` from this response is what you pass into `type=audio`.

---

### `type=audio`

```
POST /api/jiosaavn_route
Content-Type: application/json

{"query": "ID2ieOjCrwfgWvL5sXl4B1ImC5QfbsDybn6+1ArlR65DXyfmERgXytmFmYCqu6vdEDPyJ6nqm+l87Pb/ExKuGhw7tS9a8Gtq"}
```

```bash
curl -X POST http://localhost:8811/api/jiosaavn_route \
  -H "Content-Type: application/json" \
  -d '{"query": "ID2ieOjCrwfgWvL5sXl4B1ImC5QfbsDybn6+1ArlR65DXyfmERgXytmFmYCqu6vdEDPyJ6nqm+l87Pb/ExKuGhw7tS9a8Gtq"}'
```

> `encrypted_media_url` contains `+` and `/`, which get corrupted if passed
> unescaped in a querystring — that's why this one is a POST with a JSON
> body instead of `type`/`query` params. A `GET ?type=audio` request is
> rejected with `400`.

`data` is the playable stream info, valid for a limited time (~64kbps by
default — see `bitrate` in `service/jiosaavn.py:get_audio` if a higher
bitrate is needed):

```json
{
  "type": "audio",
  "query": "ID2ieOjCrwfgWvL5sXl4B1ImC5QfbsDybn6+1ArlR65DXyfmERgXytmFmYCqu6vdEDPyJ6nqm+l87Pb/ExKuGhw7tS9a8Gtq",
  "data": {
    "auth_url": "https://web.saavncdn.com/273/d1912077904b928c57eeb27b4b61d068_96.mp4?Expires=...&Signature=...&Key-Pair-Id=...",
    "type": "mp4",
    "status": "success",
    "jwe_token": "eyJhbGciOiJSU0EtT0FFUCIs..."
  },
  "stream_headers": {
    "Referer": "https://www.jiosaavn.com/"
  }
}
```

`auth_url` is the direct, time-limited (~4-5 min) URL to stream/download
the audio. **It 403s without the `Referer` header from `stream_headers`**
— the Akamai CDN behind it (`web.saavncdn.com`) checks Referer as part of
its access control, separately from the URL's own signature/expiry. Any
client consuming `auth_url` (an `<audio>` tag, ExoPlayer, curl, etc.) must
send that header on the request to the CDN, not just to this proxy:

```bash
curl -L "$AUTH_URL" -H "Referer: https://www.jiosaavn.com/" -o song.mp4
```

---

### End-to-end flow

1. `type=search` (or `autocomplete`) → get a song's `perma_url` and `encrypted_media_url`.
2. Optionally `type=song` with the id from `perma_url` to (re-)fetch full details.
3. `POST` with `encrypted_media_url` in the body → get `auth_url` to play.
