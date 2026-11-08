#!/usr/bin/env bash
# Guard for the "Publish release" step.
#
# softprops/action-gh-release will happily attach an asset to an EXISTING tag, so a manual run on
# main with make_release ticked would otherwise publish today's APK onto last month's release --
# a release whose label promises an older build. If the tag already exists it must point at this
# exact commit; if it does not exist, publishing is what creates it, which is fine.
#
# Needs the tags fetched locally, which the workflow does with fetch-depth: 0.
set -euo pipefail
cd "$(dirname "$0")/.."

TAG="${1:?usage: check_release_tag.sh <tag> [<expected-sha>]}"
SHA="${2:-${GITHUB_SHA:-$(git rev-parse HEAD)}}"

if ! git rev-parse -q --verify "refs/tags/$TAG" >/dev/null; then
  echo "tag $TAG does not exist yet -- the release step will create it at $SHA"
  exit 0
fi
AT=$(git rev-list -n 1 "$TAG")
if [ "$AT" != "$SHA" ]; then
  echo "tag $TAG already exists and points at ${AT:0:10}, not at this build ($SHA)."
  echo "Publishing here would attach this APK to an older release."
  echo "Either push a new tag, or run: git tag -f $TAG $SHA && git push -f origin $TAG"
  exit 1
fi
echo "tag $TAG points at this build ($SHA)"