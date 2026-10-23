#!/bin/bash
# Health check of both arms (nothing moves). Run this first if anything seems wrong.
KIT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$KIT/common" && python3 -m so101 check -v "$@"
