# -*- coding: utf-8 -*-
"""HTTP access to the Stream GraphQL API and to the SDN stream playlists."""

from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36"
)

# (connect, read) - without these a stalled API leaves Kodi spinning forever.
TIMEOUT = (5, 20)


class ApiError(Exception):
    """Anything that stops us from turning a request into usable data."""


def _build_session():
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
    adapter = HTTPAdapter(
        max_retries=Retry(
            total=2,
            backoff_factor=0.4,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET", "POST"]),
        )
    )
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


class StreamApi:
    ENDPOINT = "https://api.stream.cz/graphql"

    def __init__(self):
        self._session = _build_session()

    # -- GraphQL --------------------------------------------------------------

    def query(self, document, variables=None):
        """Run a GraphQL document and return its ``data`` payload."""
        payload = {"query": document, "variables": variables or {}}
        try:
            response = self._session.post(
                self.ENDPOINT, json=payload, timeout=TIMEOUT
            )
            response.raise_for_status()
            body = response.json()
        except requests.RequestException as exc:
            raise ApiError("Stream API is unreachable: {0}".format(exc))
        except ValueError:
            raise ApiError("Stream API returned a malformed response")

        errors = body.get("errors")
        if errors:
            raise ApiError(errors[0].get("message", "Unknown GraphQL error"))

        data = body.get("data")
        if data is None:
            raise ApiError("Stream API returned no data")
        return data

    # -- stream playlists -----------------------------------------------------

    def _fetch_json(self, url):
        try:
            response = self._session.get(url, timeout=TIMEOUT, allow_redirects=True)
            response.raise_for_status()
            return response.json(), response.url
        except requests.RequestException as exc:
            raise ApiError("Stream playlist is unreachable: {0}".format(exc))
        except ValueError:
            raise ApiError("Stream playlist is malformed")

    def playlist(self, spl_url):
        """Fetch the SDN playlist describing every available rendition.

        Returns ``(playlist, base_url)``; relative rendition URLs inside the
        playlist resolve against ``base_url``.
        """
        body, url = self._fetch_json(spl_url + "spl2,3,VOD")
        # SDN can answer with an in-body redirect rather than an HTTP one.
        if isinstance(body, dict) and "Location" in body:
            body, url = self._fetch_json(body["Location"])
        return body, url


def _quality_height(name):
    """'1080p' -> 1080. Returns 0 for anything unparseable."""
    digits = ""
    for char in str(name):
        if not char.isdigit():
            break
        digits += char
    return int(digits) if digits else 0


def _absolute(base_url, path):
    # Rendition URLs are relative ('../vmd_ko_x/y') or root-relative
    # ('/http-streamer/...'); urljoin handles both correctly.
    return urljoin(base_url, path).replace("|", "%7C")


# inputstream.adaptive cannot play this service, so everything below targets
# Kodi's built-in demuxer:
#   - HLS: the variant URIs in the SDN master playlist are relative and carry
#     a raw '|', which ISA refuses to resolve - playback dies at once.
#   - DASH: the manifest exposes a single muxed AdaptationSet (contentType
#     "video", codecs "avc...,mp4a..."). ISA does not demux those, so the
#     video plays without any audio.
# ffmpeg accepts both, which is why the internal player is the right target.


def _select_hls(playlist, base_url, max_height):
    """The adaptive master playlist; the player picks the variant."""
    renditions = playlist.get("pls") or {}
    for name in ("hls", "hls_fmp4"):
        stream = renditions.get(name)
        if stream and stream.get("url"):
            return {
                "url": _absolute(base_url, stream["url"]),
                "mime": "application/vnd.apple.mpegurl",
            }
    return None


def _select_progressive(playlist, base_url, max_height):
    """Highest mp4 rendition within the cap, ordered by real resolution."""
    mp4 = (playlist.get("data") or {}).get("mp4") or {}
    candidates = []
    for name, info in mp4.items():
        if not isinstance(info, dict) or not info.get("url"):
            continue
        resolution = info.get("resolution") or []
        height = resolution[1] if len(resolution) > 1 else _quality_height(name)
        if max_height and height > max_height:
            continue
        candidates.append((height, info["url"]))

    if not candidates:
        return None

    candidates.sort()
    return {
        "url": _absolute(base_url, candidates[-1][1]),
        "mime": "video/mp4",
    }


def subtitle_urls(playlist, base_url):
    """Subtitle tracks from an SDN playlist, best format first.

    Kodi reads SubRip and WebVTT over HTTP directly, so the files never have
    to be downloaded here.
    """
    tracks = (playlist.get("data") or {}).get("subtitles") or {}
    urls = []
    for track in tracks.values():
        if not isinstance(track, dict):
            continue
        available = track.get("urls") or {}
        for form in ("srt", "webvtt"):
            if available.get(form):
                urls.append(_absolute(base_url, available[form]))
                break
    return urls


def select_stream(playlist, base_url, protocol="mp4", max_height=0):
    """Pick a rendition from an SDN playlist.

    ``protocol`` is ``mp4`` (progressive, fast to start) or ``hls`` (adaptive).
    The other one is used as a fallback when the playlist lacks the preferred
    format. Returns a dict with ``url`` and ``mime``.
    """
    order = (
        (_select_progressive, _select_hls)
        if protocol == "mp4"
        else (_select_hls, _select_progressive)
    )
    for selector in order:
        stream = selector(playlist, base_url, max_height)
        if stream:
            return stream

    raise ApiError("No playable stream in the playlist")
