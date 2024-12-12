#!/usr/bin/env bash

set -eo pipefail
cd "$(dirname $0)"
[ -z "$VIRTUAL_ENV" ] && . ../env/bin/activate

[ ! -f version ] && echo "0.0.0" >version

line=$(cat version)
version=$(echo "$line" | cut -d';' -f1)
IFS='.' read -r major minor patch <<<"$version"

new_patch=$((patch + 1))
new_version="$major.$minor.$new_patch"
echo "$new_version" >version

mkdir -p webroot
tar -zcf webroot/firmware.tar.gz main.py uota.cfg version
echo "$new_version;firmware.tar.gz" >webroot/latest

curl -si http://localhost:4000/c/update

echo
echo
echo "New version: $new_version"
echo