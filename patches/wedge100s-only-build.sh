#!/bin/bash
# wedge100s-only-build.sh — Toggle between merge-ready and fast-build modes
#
# Usage:
#   ./patches/wedge100s-only-build.sh apply   # Strip to wedge100s-only (fast builds)
#   ./patches/wedge100s-only-build.sh revert  # Restore all platforms (merge-ready)
#   ./patches/wedge100s-only-build.sh status  # Show current state
#
# Apply this for local development to skip building 20+ Accton platforms
# you don't have hardware for. Revert before committing to keep the fork
# merge-ready.

set -euo pipefail

REPO_ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
RULES="$REPO_ROOT/platform/broadcom/sonic-platform-modules-accton/debian/rules"
MK="$REPO_ROOT/platform/broadcom/platform-modules-accton.mk"

die() { echo "ERROR: $*" >&2; exit 1; }

is_wedge100s_only() {
    # Check if debian/rules has only wedge100s-32x in MODULE_DIRS
    grep -q '^MODULE_DIRS := wedge100s-32x$' "$RULES" 2>/dev/null
}

do_status() {
    if is_wedge100s_only; then
        echo "BUILD MODE: wedge100s-only (fast)"
    else
        echo "BUILD MODE: all-platforms (merge-ready)"
    fi
}

do_apply() {
    if is_wedge100s_only; then
        echo "Already in wedge100s-only mode."
        exit 0
    fi

    echo "Switching to wedge100s-only build mode..."

    # --- debian/rules: replace MODULE_DIRS with wedge100s-only ---
    # Comment out existing MODULE_DIRS lines and add wedge100s-only
    sed -i \
        -e '/^MODULE_DIRS := /{s/^/#WO# /}' \
        -e '/^MODULE_DIRS += /{
            /wedge100s-32x/!{s/^/#WO# /}
        }' \
        "$RULES"

    # If there's no uncommented MODULE_DIRS := line, add one before the first #WO# line
    if ! grep -q '^MODULE_DIRS := ' "$RULES"; then
        sed -i '0,/^#WO# MODULE_DIRS := /{s/^#WO# MODULE_DIRS := .*/MODULE_DIRS := wedge100s-32x\n&/}' "$RULES"
    fi

    # --- platform-modules-accton.mk: comment out non-wedge100s blocks ---
    sed -i \
        -e '/^ACCTON_AS[0-9].*_PLATFORM_MODULE_VERSION/s/^/#WO# /' \
        -e '/^ACCTON_MINIPACK_PLATFORM_MODULE_VERSION/s/^/#WO# /' \
        -e '/^export ACCTON_AS[0-9]/s/^/#WO# /' \
        -e '/^export ACCTON_MINIPACK/s/^/#WO# /' \
        -e '/^ACCTON_AS[0-9].*_PLATFORM_MODULE = sonic-platform/s/^/#WO# /' \
        -e '/^ACCTON_MINIPACK.*_PLATFORM_MODULE = sonic-platform/s/^/#WO# /' \
        -e '/^\$(ACCTON_AS[0-9]/s/^/#WO# /' \
        -e '/^\$(ACCTON_MINIPACK/s/^/#WO# /' \
        -e '/^SONIC_DPKG_DEBS += \$(ACCTON_AS7712/s/^/#WO# /' \
        -e '/^SONIC_PLATFORM += \$(ACCTON_AS/s/^/#WO# /' \
        "$MK"

    echo "Done. Build will only compile wedge100s-32x."
    echo "Revert with: $0 revert"
}

do_revert() {
    if ! is_wedge100s_only; then
        echo "Already in all-platforms mode."
        exit 0
    fi

    echo "Restoring all-platforms (merge-ready) build mode..."

    # --- debian/rules: remove wedge100s-only line and uncomment originals ---
    sed -i \
        -e '/^MODULE_DIRS := wedge100s-32x$/d' \
        -e 's/^#WO# //' \
        "$RULES"

    # --- platform-modules-accton.mk: uncomment all ---
    sed -i 's/^#WO# //' "$MK"

    echo "Done. Build will compile all Accton platforms."
}

case "${1:-}" in
    apply)  do_apply ;;
    revert) do_revert ;;
    status) do_status ;;
    *)
        echo "Usage: $0 {apply|revert|status}"
        echo ""
        echo "  apply  — Build only wedge100s-32x (fast, for development)"
        echo "  revert — Build all Accton platforms (merge-ready, for commits)"
        echo "  status — Show current build mode"
        exit 1
        ;;
esac
