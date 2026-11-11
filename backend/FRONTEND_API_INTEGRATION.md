# Myra Frontend API Integration Guide

This document explains when the frontend should call each backend API. The
OpenAPI document is the authoritative reference for the exact request and
response schemas.

## API setup

Configure the deployed backend URL once:

```ts
const API_BASE_URL = "https://<your-backend-domain>";
```

The backend does not currently use a global `/api` prefix. For example:

```text
GET https://<your-backend-domain>/search?q=believer
```

The OpenAPI files are available at:

```text
GET /openapi.json
GET /docs
```

The frontend should send JSON with `Content-Type: application/json` for
requests with a body.

## Authentication

### Register

Call when a user creates an account:

```http
POST /users/register
Content-Type: application/json
```

```json
{
  "username": "riyansh_123",
  "pin": "123456"
}
```

The username must contain 3-30 lowercase letters, numbers, or underscores. The
PIN must contain exactly 6 digits. The backend normalizes usernames to
lowercase.

### Login

Call when an existing user signs in:

```http
POST /users/login
Content-Type: application/json
```

```json
{
  "username": "riyansh_123",
  "pin": "123456"
}
```

Both register and login return:

```json
{
  "access_token": "jwt-token",
  "token_type": "bearer",
  "user": {
    "id": "uuid",
    "username": "riyansh_123",
    "created_at": "2026-01-01T00:00:00Z"
  }
}
```

Store `access_token` securely. For authenticated endpoints, send:

```http
Authorization: Bearer <access_token>
```

### Current user and PIN

```http
GET /users/me
Authorization: Bearer <access_token>
```

Change the PIN:

```http
PATCH /users/me/pin
Authorization: Bearer <access_token>
Content-Type: application/json
```

```json
{
  "current_pin": "123456",
  "new_pin": "654321"
}
```

The successful response is `204 No Content`.

## Recommended app startup flow

After login or app startup:

1. Store or restore the access token.
2. Call `GET /users/me` to confirm that the token is valid.
3. Call `GET /player/state` to restore the current player state.
4. Call `GET /queue` to restore the user's queue.
5. Load the home screen with `GET /music/trending` and optionally
   `GET /music/recommended`.

If `/users/me` returns `401`, clear the stored token and show the login screen.

## Music discovery

These endpoints are public and do not require authentication.

### Autocomplete

Call while the user is typing, preferably with debounce:

```http
GET /search/autocomplete?q=bel
```

Response:

```json
{
  "songs": [
    {
      "jiosaavn_id": "song-id",
      "title": "Believer",
      "cover_image": "https://...",
      "album": "album name"
    }
  ],
  "artists": [
    {
      "artist_id": "artist-id",
      "title": "Imagine Dragons",
      "cover_image": "https://..."
    }
  ]
}
```

### Search

Call when the user submits a search:

```http
GET /search?q=believer&page=1&limit=10
```

`limit` is between 1 and 50.

### Trending

Call for the home/trending screen:

```http
GET /music/trending?offset=0&limit=20
```

`limit` is between 1 and 50.

### Recommended tracks

Call when recommendations are needed for a track:

```http
GET /music/recommended?track_id=<jiosaavn_id>&limit=20
```

### Track details

Call when opening a track detail page or when complete metadata is needed:

```http
GET /track/<jiosaavn_id>
```

### Artist top tracks

```http
GET /artists/<artist_id>/top-tracks?page=0&limit=20
```

The endpoint accepts `page` values starting at `0`; `limit` is between 1 and
50.

## Playback and streaming

### Get a playable stream URL

The search and track endpoints return `encrypted_media_url`. Do not play that
value directly. Pass it to:

```http
GET /track/stream/<url-encoded-encrypted-media-url>
```

Example frontend code:

```ts
const encoded = encodeURIComponent(song.encrypted_media_url);
const stream = await api.get(`/track/stream/${encoded}`);

audio.src = stream.playback_url;
// Apply every header in stream.playback_headers when using a native player
// that supports request headers.
```

Response:

```json
{
  "playback_url": "https://...",
  "playback_headers": {
    "Referer": "https://www.jiosaavn.com/"
  }
}
```

The playback URL is signed and temporary. Request a new one when it expires.
The CDN may reject playback if the returned headers are not sent.

### Select and start a track

When the user taps a track, update the player state:

```http
PATCH /player/state
Authorization: Bearer <access_token>
Content-Type: application/json
```

```json
{
  "jiosaavn_id": "song-id",
  "is_playing": true
}
```

Selecting a different track:

- makes it the current track;
- clears the existing queue;
- resets the position to `0`;
- records a play when playback starts;
- adds artist recommendations to the queue.

After this request, fetch the stream URL and start the audio player.

### Update player state

The frontend should periodically save playback state and save it when the
player is paused, resumed, seeked, or closed:

```http
PATCH /player/state
Authorization: Bearer <access_token>
Content-Type: application/json
```

All fields are optional:

```json
{
  "is_playing": false,
  "shuffle": true,
  "repeat_mode": "off",
  "position_seconds": 42
}
```

`repeat_mode` must be one of `off`, `one`, or `all`.

The response includes the updated player state and queue:

```json
{
  "current_track": {},
  "is_playing": false,
  "shuffle": true,
  "repeat_mode": "off",
  "position_seconds": 42,
  "queue": [],
  "queue_total": 0
}
```

### Restore player state

```http
GET /player/state
Authorization: Bearer <access_token>
```

### Next and previous

Call when the user taps next or previous:

```http
POST /player/next
Authorization: Bearer <access_token>
```

```http
POST /player/previous
Authorization: Bearer <access_token>
```

The response is the new player state. After receiving the new current track,
request its stream URL and start playback. `next` can automatically use
recommendations when the queue has no next track.

## Queue

### Read the queue

```http
GET /queue
Authorization: Bearer <access_token>
```

Call this after login, app startup, queue changes, and after an assistant
action that may change playback or the queue.

### Add a track

```http
POST /queue/tracks
Authorization: Bearer <access_token>
Content-Type: application/json
```

```json
{
  "jiosaavn_id": "song-id"
}
```

### Remove a queued item

Use the `queue_id` returned by `GET /queue` or `POST /queue/tracks`:

```http
DELETE /queue/tracks/<queue_id>
Authorization: Bearer <access_token>
```

Successful response: `204 No Content`.

### Reorder the queue

Send every current queue ID exactly once, in the desired order:

```http
PATCH /queue/reorder
Authorization: Bearer <access_token>
Content-Type: application/json
```

```json
{
  "positions": [21, 18, 19]
}
```

The response is the refreshed queue.

### Clear the queue

```http
DELETE /queue
Authorization: Bearer <access_token>
```

Successful response: `204 No Content`.

## Favorites and listening history

### Add or remove a favorite

```http
PUT /library/favorites/<jiosaavn_id>
Authorization: Bearer <access_token>
```

The response contains the saved track:

```json
{
  "favorite": true,
  "track": {}
}
```

Remove it:

```http
DELETE /library/favorites/<jiosaavn_id>
Authorization: Bearer <access_token>
```

Successful response: `204 No Content`.

### List favorites

```http
GET /library/favorites?offset=0&limit=20
Authorization: Bearer <access_token>
```

### Record a play explicitly

```http
POST /history/recently-played/<jiosaavn_id>
Authorization: Bearer <access_token>
```

Normally the frontend should not call this when it uses
`PATCH /player/state` to start a track, because starting playback through the
player state already records the play.

### Recently played

```http
GET /history/recently-played?offset=0&limit=20
Authorization: Bearer <access_token>
```

### Most played

```http
GET /library/most-played?offset=0&limit=20
```

This endpoint is public in the current backend implementation.

## Playlists

All playlist endpoints require authentication.

### Create a playlist

```http
POST /playlists
Authorization: Bearer <access_token>
Content-Type: application/json
```

```json
{
  "name": "Road Trip",
  "description": "Songs for driving"
}
```

`description` is optional.

### List playlists

```http
GET /playlists?offset=0&limit=20
Authorization: Bearer <access_token>
```

### Get playlist details

```http
GET /playlists/<playlist_id>?offset=0&limit=20
Authorization: Bearer <access_token>
```

### Add a track to a playlist

```http
POST /playlists/<playlist_id>/tracks
Authorization: Bearer <access_token>
Content-Type: application/json
```

```json
{
  "jiosaavn_id": "song-id"
}
```

### Remove a track from a playlist

The path parameter is the playlist-track record ID returned by the playlist
response, not the JioSaavn track ID:

```http
DELETE /playlists/<playlist_id>/tracks/<track_id>
Authorization: Bearer <access_token>
```

### Rename or update a playlist

```http
PATCH /playlists/<playlist_id>
Authorization: Bearer <access_token>
Content-Type: application/json
```

```json
{
  "name": "Updated name",
  "description": "Updated description"
}
```

### Delete a playlist

```http
DELETE /playlists/<playlist_id>
Authorization: Bearer <access_token>
```

All successful delete operations return `204 No Content`.

## AI assistant

### Send a chat message

```http
POST /assistant/chat
Authorization: Bearer <access_token>
Content-Type: application/json
```

First message:

```json
{
  "message": "Play some songs by Imagine Dragons",
  "metaData": {
    "current_track_id": null,
    "is_playing": false,
    "position_seconds": 0
  }
}
```

For every later message, send the `session` object returned by the previous
assistant response:

```json
{
  "message": "Skip this song",
  "metaData": {
    "current_track_id": "song-id",
    "is_playing": true,
    "position_seconds": 35
  },
  "session": {
    "chat_id": "chat-id",
    "bx_umidtoken": "token",
    "model": "qwen3.7-plus",
    "parent_id": "parent-id"
  }
}
```

The response contains:

```json
{
  "message": "Playing ...",
  "message_type": "text",
  "metadata": null,
  "session": {}
}
```

`message_type` can be:

| Value | Frontend behavior |
|---|---|
| `text` | Display `message` normally. |
| `song` | Display `message`, then use `metadata.playback_url` and `metadata.playback_headers` if present. Refresh the queue with `GET /queue`. |
| `function_call` | Execute the requested player action locally, then refresh player state and/or queue. |

For `function_call`, the metadata has this shape:

```json
{
  "function_name": "next",
  "arguments": {}
}
```

Supported player actions are:

| Action | Frontend operation |
|---|---|
| `pause` | Pause the local audio player, then save `is_playing: false`. |
| `resume` | Resume the local audio player, then save `is_playing: true`. |
| `next` | Call `POST /player/next`, fetch the returned track stream, and play it. |
| `previous` | Call `POST /player/previous`, fetch the returned track stream, and play it. |
| `seek_forward` | Seek forward by `arguments.seconds`. |
| `seek_backward` | Seek backward by `arguments.seconds`. |
| `seek_to` | Seek to `arguments.seconds` from the start. |

After a function call that changes the queue or current track, call:

```http
GET /player/state
GET /queue
```

The assistant session must be preserved independently from the access token.
If the session is omitted, the backend starts a new assistant conversation.

## Typical play flow

1. User searches: `GET /search?q=...`.
2. User taps a result: `PATCH /player/state` with `jiosaavn_id` and
   `is_playing: true`.
3. Frontend requests `GET /track/stream/<encoded encrypted_media_url>`.
4. Frontend plays `playback_url` using `playback_headers`.
5. Frontend periodically saves `position_seconds` with
   `PATCH /player/state`.
6. User taps next: `POST /player/next`, then fetches and plays the new stream.
7. User opens the queue: `GET /queue`.

When a track is started through player state, the backend manages the current
track, play history, and artist recommendations automatically.

## Common errors

Most errors use this shape:

```json
{
  "detail": "Human-readable error message"
}
```

Important status codes:

| Status | Meaning |
|---:|---|
| `400` | Invalid request or invalid queue reorder. |
| `401` | Missing or invalid bearer token. |
| `403` | Authenticated but not allowed to perform the operation. |
| `404` | Track, playlist, queue item, or stream was not found. |
| `409` | Username or resource conflict. |
| `422` | Request validation failed. |
| `429` | Too many failed login attempts; respect the `Retry-After` header. |
| `502` | Music provider or AI assistant is temporarily unavailable. |

For `204 No Content`, do not attempt to parse a JSON response body.

## Health check

Use this endpoint for deployment or service monitoring:

```http
GET /health
```

Response:

```json
{
  "status": "healthy"
}
```

