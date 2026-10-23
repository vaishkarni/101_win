#!/bin/bash
# Build one zip per platform: so101_kit_jetson.zip and so101_kit_x86.zip (each = README + common/ + that platform folder).
set -e; cd "$(dirname "$0")"
find common -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
for p in jetson x86; do
  rm -f so101_kit_$p.zip
  zip -qr so101_kit_$p.zip README.md common $p -x 'common/tests/*' 'common/*.pyc'
  echo "built so101_kit_$p.zip ($(du -h so101_kit_$p.zip | cut -f1))"
done
