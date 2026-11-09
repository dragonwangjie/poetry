#!/usr/bin/env bash
# Work out what version this build is, and export it to GITHUB_OUTPUT as name=/code=.
#
# AndroidManifest.xml is the single source of truth for BOTH numbers: the APK's own version comes
# from it, so anything else the Release page displayed would be a second, possibly disagreeing,
# label. versionCode in particular must not be invented from a tag -- Android compares that
# integer to decide whether an install is an upgrade, and a tag-derived one could ship lower than
# the previous release, which then silently refuses to update in place.
#
# On a tag push the tag is only CHECKED, never used as the value: v1.19 / release-1.19 must agree
# with android:versionName (an -rcN suffix is tolerated) or the run fails. Otherwise the file a
# user downloads would claim to be a different build than the release page says it is.
set -euo pipefail

cd "$(dirname "$0")/.."
MAN=app/AndroidManifest.xml
VC=$(sed -n 's/.*android:versionCode="\([0-9]*\)".*/\1/p' "$MAN" | head -1)
VN=$(sed -n 's/.*android:versionName="\([^"]*\)".*/\1/p' "$MAN" | head -1)
[ -n "$VC" ] && [ -n "$VN" ] || { echo "cannot read versionCode/versionName from $MAN"; exit 1; }

# Is THIS a tag run? Decide from the ref GitHub told us, never by pattern-matching the name: a
# branch called v2-refactor starts with "v" too, and guessing would run the tag-vs-manifest check
# on an ordinary branch push and fail it with a message about tags that has nothing to do with
# what the user did. The workflow passes both values explicitly (ref_type is 'tag' or 'branch').
REF_TYPE="${REF_TYPE:-${GITHUB_REF_TYPE:-}}"
REF="${GITHUB_REF_NAME:-}"
if [ "$REF_TYPE" = tag ]; then :
elif [ -n "$REF_TYPE" ]; then REF=''      # branch run: no tag to check or reuse
elif [ "${REF#release-}" != "$REF" ] || [ "${REF#v}" != "$REF" ]; then
  # REF_TYPE unknown (running this script by hand): fall back to the naming convention, which is
  # exactly what a person means when they set GITHUB_REF_NAME=v1.19 to try the check locally.
  REF="$REF"
else
  REF=''
fi

TAG=''
if [ -n "$REF" ]; then
  if [ "${REF#release-}" != "$REF" ]; then TAG="${REF#release-}";
  elif [ "${REF#v}" != "$REF" ]; then TAG="${REF#v}"; fi
fi

if [ -n "$TAG" ]; then
  # accept "1.19" and also "1.19-rc2" against a manifest that says 1.19
  case "$TAG" in
    "$VN") : ;;
    "$VN"-*) echo "::warning::tag $REF carries a suffix ($TAG vs manifest $VN); building as $VN" ;;
    *)
      echo "tag '$REF' does not match android:versionName='$VN' in $MAN"
      echo "bump android:versionName (and versionCode) in app/AndroidManifest.xml, commit, then retag."
      echo "Refusing to publish: the APK takes its version from the manifest, so the download"
      echo "would report a different version than the release title."
      exit 1 ;;
  esac
fi

OUT_TAG="$REF"
[ -n "$TAG" ] || OUT_TAG="v$VN"      # manual run: publish onto v<versionName>, created if absent

if [ -n "${GITHUB_OUTPUT:-}" ]; then
  printf 'code=%s\nname=%s\ntag=%s\n' "$VC" "$VN" "$OUT_TAG" >> "$GITHUB_OUTPUT"
fi
echo "version $VN (code $VC) from $MAN"
echo "release tag would be: $OUT_TAG${TAG:+ (pushed tag, already checked)}"