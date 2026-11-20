#!/usr/bin/env bash
# Fetch Xiaomi's protobuf definitions from Gadgetbridge and regenerate the Python
# bindings in src/xiaomi_pb/.
#
# proto/ and src/xiaomi_pb/ are both git-ignored -- proto/ is vendored from Gadgetbridge
# (AGPL-3.0) and the bindings are generated from it -- so a fresh clone has neither.
# This script bootstraps both:
#
#   ./fetch_protos.sh                # download protos, then regenerate src/xiaomi_pb/
#   ./fetch_protos.sh --protos-only  # download protos only
#
#   GADGETBRIDGE_REF=<commit-or-tag> ./fetch_protos.sh   # pin something else
#
# Upstream: https://codeberg.org/Freeyourgadget/Gadgetbridge
# Pinned:   93d4d79a175db6e64a8670658651772072c5915c (2026-11-15)
#
# The pinned files are verified against the SHA-256 sums below; if GADGETBRIDGE_REF
# points anywhere else the check is skipped. Bumping the pin means updating both the
# ref and those sums, and adding a line if upstream grew a new .proto file.
set -euo pipefail

PINNED_REF=93d4d79a175db6e64a8670658651772072c5915c
REF="${GADGETBRIDGE_REF:-$PINNED_REF}"
REPO=https://codeberg.org/Freeyourgadget/Gadgetbridge
SUBDIR=GBProtobufGenerator/src/main/proto
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

# path relative to proto/ -> sha256 at the pinned ref
declare -A SHA256=(
  [xiaomi.proto]=b01269435f6f8c62710b360867c70366f9961c58ba0184c55863f2aaafa03801
  [xiaomi/wear_account.proto]=47758cc438238e05e8d3c4af5a9cad88b2da0c3bf873ce2b83d931e252aa0c69
  [xiaomi/wear_calendar.proto]=ee956604029e948c8d112be956d0e2bca97be467c9713b9ffc363dddd9214c7d
  [xiaomi/wear_clock.proto]=1bd65ad031e61a456627cae689c763f2476913f38e522c5ca76eb7491fd364f0
  [xiaomi/wear_common.proto]=a38ee819e9eadaf31754c7b866847b40fc470f2f4a3175778758211a1541a7e6
  [xiaomi/wear_contact.proto]=597727997cefb2fccc2c7f73bf9e212afbf157d5527c965205a96c28fc4668ab
  [xiaomi/wear_fitness.proto]=0ac5e867a2bc0d93dcd5b9822b248f48143e377053fbb265f4636c814acf1a42
  [xiaomi/wear_mass.proto]=c2076a605e324dae44dc8732ddbe63c0cbc3599cc8a41c3dea0b6ed62917971d
  [xiaomi/wear_media.proto]=21e2fc61684b83975229034bd60ee6865eb4478f2c21041da2a85ae50a8a6336
  [xiaomi/wear_notification.proto]=eae6c05e98af791d5ee8de5862d6b4b5854572225d19a1425adc22db468456a6
  [xiaomi/wear_system.proto]=24835ba51c7722e003ad25cbfeadd1bd77dea3e1e5ceae7bc1b924a4878efc05
  [xiaomi/wear_thirdparty_app.proto]=65a2670aa00384efb4b84f7fecd8000a15df913132be69a598a97bb0a7e495a2
  [xiaomi/wear_watch_face.proto]=594163cad970f5ec4045bfa21b5b8651875ebdaaccc35e7ba272f7a539edcb81
  [xiaomi/wear_weather.proto]=6a2a3feb99e5cf50a31efc36fa109440f74c40ccb2d1cf4c89cc5d6df4af5ad7
)

protos_only=0
case "${1:-}" in
  --protos-only) protos_only=1 ;;
  "") ;;
  *) echo "usage: $0 [--protos-only]" >&2; exit 2 ;;
esac

for tool in curl tar sha256sum; do
  command -v "$tool" >/dev/null 2>&1 || { echo "error: $tool is required" >&2; exit 1; }
done

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
staging="$tmp/proto"
mkdir -p "$staging/xiaomi"

echo "Fetching ${#SHA256[@]} protos from Gadgetbridge @ ${REF:0:12} ..."
if [ "$REF" != "$PINNED_REF" ]; then
  echo "note: GADGETBRIDGE_REF overrides the pin, so checksums are not verified" >&2
fi
for path in "${!SHA256[@]}"; do
  url="$REPO/raw/commit/$REF/$SUBDIR/$path"
  curl -fsSL --retry 3 -o "$staging/$path" "$url" || {
    echo "error: failed to download $path from $url" >&2
    exit 1
  }
  if [ "$REF" = "$PINNED_REF" ]; then
    got=$(sha256sum "$staging/$path" | cut -d' ' -f1)
    [ "$got" = "${SHA256[$path]}" ] || {
      echo "error: checksum mismatch for $path" >&2
      echo "  expected ${SHA256[$path]}" >&2
      echo "  got      $got" >&2
      exit 1
    }
  fi
done

cat > "$staging/SOURCE.md" <<EOF
# Copied from Gadgetbridge (AGPL-3.0):
# $REPO
# ref $REF
# path $SUBDIR
#
# Regenerate this directory and src/xiaomi_pb/ with ./fetch_protos.sh
EOF

rm -rf "$HERE/proto"
mv "$staging" "$HERE/proto"
echo "Wrote $HERE/proto (${#SHA256[@]} .proto files + SOURCE.md)"

if (( protos_only )); then
  exit 0
fi

# Importable layout: src/xiaomi_client.py puts src/xiaomi_pb on sys.path and the
# generated modules import each other as `from xiaomi import ...`, so the output
# directory is fixed. Paths are relative to the repository root.
OUT=src/xiaomi_pb
cd "$HERE"
mkdir -p "$OUT"
echo "Regenerating $OUT/ ..."
if command -v uv >/dev/null 2>&1; then
  uv run python -m grpc_tools.protoc -Iproto --python_out="$OUT" \
    proto/xiaomi.proto proto/xiaomi/*.proto
else
  echo "uv not found, falling back to python3 (needs grpcio-tools installed)" >&2
  python3 -m grpc_tools.protoc -Iproto --python_out="$OUT" \
    proto/xiaomi.proto proto/xiaomi/*.proto
fi

[ -f "$OUT/xiaomi_pb2.py" ] || { echo "error: $OUT/xiaomi_pb2.py was not generated" >&2; exit 1; }
modules=$(find "$OUT/xiaomi" -maxdepth 1 -name '*_pb2.py' | wc -l)
echo "Wrote $HERE/$OUT (xiaomi_pb2.py + $modules wear_*_pb2 modules)"
