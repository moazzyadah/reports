#!/usr/bin/env python3
"""Send a WhatsApp message via Evolution API. Used by GitHub Actions after report generation."""

import sys
import os
import httpx

EVOLUTION_URL = os.environ["EVOLUTION_URL"]
EVOLUTION_KEY = os.environ["EVOLUTION_API_KEY"]
WHATSAPP_NUMBER = os.environ["WHATSAPP_NUMBER"]

text = sys.stdin.read().strip()
if not text:
    print("No text to send", file=sys.stderr)
    sys.exit(1)

# Split into chunks if over WhatsApp limit (~4000 chars)
chunks = [text[i:i+3900] for i in range(0, len(text), 3900)]

for chunk in chunks:
    r = httpx.post(
        f"{EVOLUTION_URL}/message/sendText/Whatsapp-test",
        headers={"apikey": EVOLUTION_KEY, "Content-Type": "application/json"},
        json={"number": WHATSAPP_NUMBER, "text": chunk},
        timeout=30,
    )
    r.raise_for_status()

print(f"Sent {len(chunks)} message(s)")
