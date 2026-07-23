#!/usr/bin/env python3
"""
relay_example.py -- Optimized TTS relay for CC:Tweaked (DFPWM output with speech enhancement)
"""

import http.server
import json
import re
import subprocess
import sys

HOST = "0.0.0.0"
PORT = 5005


def synthesize_wav(text: str) -> bytes:
    """Text -> WAV bytes using espeak-ng with optimized voice parameters."""
    cleaned_text = re.sub(r"[^\w\s.,!?-]", "", text).strip()
    if not cleaned_text:
        cleaned_text = "Hello"

    # -s 150 sets a clear speaking speed, -p 50 is default pitch
    result = subprocess.run(
        ["espeak-ng", "-s", "150", "-v", "en-us", "--stdout", cleaned_text],
        capture_output=True,
        check=True,
    )
    return result.stdout


def optimize_and_convert_to_dfpwm(wav_bytes: bytes) -> bytes:
    """
    Applies an audio filter chain optimized for human speech (highpass/lowpass filters,
    equalization for vocal presence, dynamic range compression) then encodes to DFPWM.
    """
    # Audio filter explanation:
    # 1. highpass=f=200: removes low-end rumble and pops
    # 2. lowpass=f=3000: cuts harsh high-frequency artifacts out of espeak
    # 3. equalizer=f=1000:width_type=h:w=200:g=3: boosts clarity in the vocal range
    # 4. dynaudnorm: dynamic audio normalization for consistent, crisp volume
    audio_filters = (
        "highpass=f=200,"
        "lowpass=f=3000,"
        "equalizer=f=1000:width_type=h:w=400:g=4,"
        "dynaudnorm=f=150:g=15"
    )

    result = subprocess.run(
        [
            "ffmpeg",
            "-loglevel",
            "error",
            "-i",
            "pipe:0",
            "-af",
            audio_filters,
            "-f",
            "dfpwm",
            "-ar",
            "48000",
            "-ac",
            "1",
            "pipe:1",
        ],
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
        self.wfile.write(
            b"Optimized TTS Relay is running. Send a POST request to /tts with JSON."
        )

    def do_POST(self):
        if self.path != "/tts":
            self.send_response(404)
            self.end_headers()
            return

        length = int(self.headers.get("Content-Length", 0))
        try:
            body = self.rfile.read(length) if length > 0 else b"{}"
            payload = json.loads(body.decode("utf-8") or "{}")
            text = (payload.get("text") or "").strip()
            if not text:
                raise ValueError("empty 'text' field")

            wav = synthesize_wav(text)
            dfpwm_data = optimize_and_convert_to_dfpwm(wav)

            self.send_response(200)
            self.send_header("Content-Type", "audio/dfpwm")
            self.send_header("Content-Length", str(len(dfpwm_data)))
            self.end_headers()
            self.wfile.write(dfpwm_data)
        except subprocess.CalledProcessError as e:
            self.send_response(500)
            self.end_headers()
            err_msg = (
                e.stderr.decode("utf-8", errors="ignore")
                if e.stderr
                else str(e)
            )
            self.wfile.write(f"synthesis/conversion failed: {err_msg}".encode())
        except Exception as e:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(str(e).encode())

    def log_message(self, fmt, *args):
        print(
            f"[relay] {self.address_string()} - {fmt % args}", file=sys.stderr
        )


if __name__ == "__main__":
    server = http.server.ThreadingHTTPServer((HOST, PORT), Handler)
    print(
        f"Optimized TTS relay listening on http://{HOST}:{PORT}/tts"
    )
    server.serve_forever()
