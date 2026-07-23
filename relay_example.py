#!/usr/bin/env python3
"""
relay_example.py -- minimal illustrative TTS relay for tts.lua

This is a STARTING POINT, not a finished product. It exists to solve one
specific problem: CC:Tweaked speakers only play raw 8-bit signed PCM audio
at 48000Hz mono, and no mainstream TTS engine (cloud or offline) outputs
that format directly. This script:

  1. runs a tiny HTTP server
  2. accepts  POST /tts   body: {"text": "..."}
  3. synthesizes speech for that text with espeak-ng (offline, no API key,
     easy to swap for a cloud TTS engine -- see synthesize_wav() below)
  4. uses ffmpeg to convert the result to raw s8 / 48000Hz / mono
  5. returns those raw bytes as the response body

REQUIREMENTS on the machine running this relay (not on the Minecraft
server): `espeak-ng` and `ffmpeg` on PATH.
    Debian/Ubuntu: sudo apt install espeak-ng ffmpeg

RUN:
    python3 relay_example.py                # listens on 0.0.0.0:5005
Then point TTS_ENDPOINT in main.lua at "http://<this-machine's-ip>:5005/tts"
and add that IP to the CC:Tweaked http allow-list.
"""

import http.server
import json
import re
import subprocess
import sys

HOST = "0.0.0.0"
PORT = 5005


def synthesize_wav(text: str) -> bytes:
    """Text -> WAV bytes, using the offline espeak-ng engine after cleaning characters."""
    # Strip out emojis, weird symbols, or characters that might crash espeak-ng
    cleaned_text = re.sub(r'[^\w\s.,!?-]', '', text)
    
    result = subprocess.run(
        ["espeak-ng", "-s", "165", "--stdout", cleaned_text],
        capture_output=True,
        check=True,
    )
    return result.stdout


def wav_to_raw_pcm_s8_48k_mono(wav_bytes: bytes) -> bytes:
    """WAV (any sample rate/format) -> raw 8-bit signed PCM, 48kHz, mono."""
    result = subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-i", "pipe:0",
         "-f", "s8", "-ar", "48000", "-ac", "1", "pipe:1"],
        input=wav_bytes,
        capture_output=True,
        check=True,
    )
    return result.stdout


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"TTS Relay is running. Send a POST request to /tts with JSON.")

    def do_POST(self):
        if self.path != "/tts":
            self.send_response(404)
            self.end_headers()
            return

        length = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
            text = (payload.get("text") or "").strip()
            if not text:
                raise ValueError("empty 'text' field")

            wav = synthesize_wav(text)
            pcm = wav_to_raw_pcm_s8_48k_mono(wav)

            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(pcm)))
            self.end_headers()
            self.wfile.write(pcm)
        except subprocess.CalledProcessError as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(f"synthesis failed: {e}".encode())
        except Exception as e:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(str(e).encode())

    def log_message(self, fmt, *args):
        print(f"[relay] {self.address_string()} - {fmt % args}", file=sys.stderr)


if __name__ == "__main__":
    server = http.server.ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"TTS relay listening on http://{HOST}:{PORT}/tts")
    server.serve_forever()
