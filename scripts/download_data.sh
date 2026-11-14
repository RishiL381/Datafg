#!/usr/bin/env bash
# Downloads the datathon raw data from the team Google Drive folder into ./data
# Source folder: https://drive.google.com/drive/folders/1l4JdVQOm5iaS0WO0tQ1PL-fCtqWT_8aj
# Files are link-shared ("anyone with link"), so plain curl works.
# Run from repo root:  bash scripts/download_data.sh
set -euo pipefail
cd "$(dirname "$0")/.."

dl () {  # dl <file_id> <dest_path>
  local id="$1" dest="$2"
  if [[ -s "$dest" ]]; then echo "skip (exists): $dest"; return; fi
  mkdir -p "$(dirname "$dest")"
  echo "downloading $dest"
  curl -sSL --retry 5 -C - -o "$dest.part" \
    "https://drive.usercontent.google.com/download?id=${id}&export=download&confirm=t"
  mv "$dest.part" "$dest"
  echo "done: $dest ($(du -h "$dest" | cut -f1))"
}

# Google Maps places (~506 MB)
dl 1T9ftw9sEYKD9JiCNah4L_vPxQ8nEnrE2 data/google_maps/google_maps.csv &
dl 1UNLZ2SzgjzI67yGPxssHIn3-G6qhCor4 data/google_maps/google_maps_reviews_sample.csv &
# Google Maps reviews (~222 MB)
dl 1Ov_U0PP9i7DYmrtvnbPBLtboDSOo1SwB data/google_maps_reviews/google_maps_reviews.csv &
# Zillow (~7.4 GB total across 3 parts) + 41 MB sample
dl 1-QWqAOXDJ2S4mxOn_YO960XGok2qTcV5 data/zillow/zillow_sample.csv &
dl 1Iwve7-R3v4co0pOAzle9aFD8g5RE0nOS data/zillow/zillow_part1.csv &
dl 1ny6Ow4jSN6zflFuEJL1issGesKj5pcIM data/zillow/zillow_part2.csv &
dl 1wmidTapYv70pmHuzd3xa6TskLJGZCgkD data/zillow/zillow_part3.csv &
wait
echo "ALL DOWNLOADS DONE"
