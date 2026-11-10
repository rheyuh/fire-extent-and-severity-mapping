#!/usr/bin/env bash
# Put every input for one fire onto the same grid, so pixel [row, col] is the same ground in all.
#
# 1. ogr2ogr: cut the fire's outline out of the NPWS shapefile, in the grid's CRS.
# 2. gdalwarp: reproject, resample and clip each input to that outline. -tap snaps the edges to
#    whole multiples of RES, so all outputs share the same pixels.
#
# Values come from environment variables (set by run.py, or by hand to test):
#   OUT_DIR, OUTLINE_SHP, FIRE_NO_FIELD, FIRE_NO, CRS, RES, FESM,
#   PRE_NIR, PRE_SWIR2, PRE_FMASK, POST_NIR, POST_SWIR2, POST_FMASK

# Stop at the first failed command or unset variable, instead of carrying on with a missing file.
set -euo pipefail
# DEA's bucket is public: read it without AWS keys.
export AWS_NO_SIGN_REQUEST=YES

out="${OUT_DIR:?}"
outline="$out/outline.gpkg"
mkdir -p "$out"

ogr2ogr -f GPKG -overwrite -t_srs "${CRS:?}" \
  -where "${FIRE_NO_FIELD:?} = '${FIRE_NO:?}'" \
  "$outline" "${OUTLINE_SHP:?}"

# warp SRC DST RESAMPLING NODATA
warp() {
  # -ovr NONE: always read full-resolution pixels. Otherwise GDAL may read FESM's pre-built
  # overviews (made with their own resampling) when going from ~10 m to 20 m.
  gdalwarp -q -overwrite -ovr NONE \
    -t_srs "$CRS" -tr "${RES:?}" "$RES" -tap \
    -cutline "$outline" -crop_to_cutline \
    -r "$3" -dstnodata "$4" \
    -co COMPRESS=DEFLATE \
    "$1" "$out/$2"
}

# Reflectance: bilinear (a measurement). Class maps: near / mode (averaging would invent classes).
warp "${PRE_NIR:?}"    pre_nir.tif    bilinear -999
warp "${PRE_SWIR2:?}"  pre_swir2.tif  bilinear -999
warp "${PRE_FMASK:?}"  pre_fmask.tif  near     0
warp "${POST_NIR:?}"   post_nir.tif   bilinear -999
warp "${POST_SWIR2:?}" post_swir2.tif bilinear -999
warp "${POST_FMASK:?}" post_fmask.tif near     0
warp "${FESM:?}"       fesm.tif       mode     255

# Outline mask on the same grid: 1 inside the fire, 0 outside. Lets the QA checks tell
# "outside the outline" apart from "inside, but masked by cloud".
gdal_create --quiet -if "$out/pre_nir.tif" -ot Byte -burn 0 -a_nodata 255 "$out/outline.tif"
gdal_rasterize -q -burn 1 "$outline" "$out/outline.tif"

# One line per output: if the grids line up, every size and origin is identical.
for f in "$out"/*.tif; do
  printf '%-16s ' "$(basename "$f")"
  gdalinfo "$f" | grep -E '^(Size is|Origin)' | tr '\n' ' '
  echo
done
