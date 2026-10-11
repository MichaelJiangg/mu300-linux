#!/bin/sh
# Build mu300-voice-events as a static arm64 binary (libc only).
#   tools/voice-events/build.sh [OUT]   default: tools/voice-events/mu300-voice-events - install it as
#                                       /opt/mu300/bin/mu300-voice-events (mu300-voice watch starts it)
set -eu
HERE=$(cd "$(dirname "$0")" && pwd); OUT=${1:-$HERE/mu300-voice-events}
docker run --rm --platform linux/arm64 -v "$HERE":/w alpine sh -c \
  'apk add -q gcc musl-dev && gcc -Wall -O2 -static -o /w/mu300-voice-events.out /w/mu300-voice-events.c'
mv "$HERE/mu300-voice-events.out" "$OUT"; echo "built $OUT"
