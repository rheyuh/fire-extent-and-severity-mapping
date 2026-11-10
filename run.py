"""Compare a Sentinel-2 dNBR burn-severity map with NSW FESM for one fire.

Run: uv run python run.py --config config.yaml
"""

import argparse
import csv
import hashlib
import json
import os
import platform
import subprocess
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
import yaml

SEVERITY_NODATA = 255  # same as FESM's nodata, so both class maps use one code


def load_config(path: Path) -> dict[str, Any]:
    config: dict[str, Any] = yaml.safe_load(path.read_text())
    return config


def prepare(config: dict[str, Any], work: Path) -> None:
    """Run scripts/prepare.sh: every input clipped and warped onto one grid in `work`."""
    scenes = config["scenes"]
    env = {
        "OUT_DIR": str(work),
        "OUTLINE_SHP": config["inputs"]["outline"],
        "FIRE_NO_FIELD": config["inputs"]["fire_no_field"],
        "FIRE_NO": config["fire"]["npws_fire_no"],
        "CRS": config["grid"]["crs"],
        "RES": str(config["grid"]["resolution"]),
        "FESM": config["inputs"]["fesm"],
    }
    for when in ("pre", "post"):
        for band in ("nir", "swir2", "fmask"):
            env[f"{when}_{band}".upper()] = scenes[when][band]
    # check=True: stop here if any GDAL command in the script fails.
    subprocess.run(["bash", "scripts/prepare.sh"], env={**os.environ, **env}, check=True)


def read(path: Path) -> tuple[np.ndarray, dict[str, Any]]:
    """Band 1 of a GeoTIFF, and its profile (CRS, transform, size) for writing outputs."""
    with rasterio.open(path) as src:
        return src.read(1), dict(src.profile)


def nbr(nir: np.ndarray, swir2: np.ndarray) -> np.ndarray:
    """Normalised Burn Ratio, (NIR - SWIR2) / (NIR + SWIR2). The x10,000 scale cancels out."""
    nir = nir.astype("float32")
    swir2 = swir2.astype("float32")
    with np.errstate(divide="ignore", invalid="ignore"):  # nodata pixels are masked afterwards
        ratio: np.ndarray = (nir - swir2) / (nir + swir2)
    return ratio


def masked_nbr(work: Path, when: str, config: dict[str, Any]) -> np.ndarray:
    """NBR for one date, NaN wherever a band is nodata or fmask is not clear."""
    nir, _ = read(work / f"{when}_nir.tif")
    swir2, _ = read(work / f"{when}_swir2.tif")
    fmask, _ = read(work / f"{when}_fmask.tif")
    nodata = config["bands"]["nodata"]
    valid = np.isin(fmask, config["bands"]["fmask_clear"]) & (nir != nodata) & (swir2 != nodata)
    return np.where(valid, nbr(nir, swir2), np.nan)


def classify(dnbr: np.ndarray, thresholds: list[float], classes: list[int]) -> np.ndarray:
    """dNBR to severity classes, as uint8. NaN (no data) becomes SEVERITY_NODATA.

    thresholds [0.10, 0.27, 0.44, 0.66] and classes [0, 2, 3, 4, 5] give:
        dNBR < 0.10 -> 0,  0.10 <= dNBR < 0.27 -> 2,  ...,  dNBR >= 0.66 -> 5
    """
    # Bin 0-4: how many thresholds each value is at or above (a value on a threshold goes up).
    bins = np.digitize(dnbr, thresholds)
    # Bins to FESM codes: bin 1 is class 2, because FESM's class 1 (grassland) has no severity.
    severity = np.asarray(classes)[bins]
    # digitize puts NaN in the top bin; without this, masked pixels would read as "extreme".
    return np.where(np.isnan(dnbr), SEVERITY_NODATA, severity).astype("uint8")


def confusion(yours: np.ndarray, fesm: np.ndarray, classes: list[int]) -> np.ndarray:
    """Pixel counts: rows are your class, columns FESM's, both in `classes` order.

    Only pixels where both maps hold one of `classes` are counted, so nodata (255) and FESM's
    grassland class (1, no severity order) drop out.
    """
    keep = np.isin(yours, classes) & np.isin(fesm, classes)
    # Class code to row/column number, e.g. [0, 2, 3, 4, 5] -> 0..4 (classes are in order).
    row = np.searchsorted(classes, yours[keep])
    col = np.searchsorted(classes, fesm[keep])
    n = len(classes)
    # Count each (row, col) pair: pair k = row * n + col, then fold back into n x n.
    counts: np.ndarray = np.bincount(row * n + col, minlength=n * n).reshape(n, n)
    return counts


def agreement(matrix: np.ndarray) -> dict[str, float]:
    """Summary of a confusion matrix, in % of compared pixels."""
    total = int(matrix.sum())
    if total == 0:
        raise ValueError("no pixels to compare: check the outline, masks and FESM clip")
    row, col = np.indices(matrix.shape)  # row = your class, col = FESM's
    return {
        "pixels": total,
        "exact_pct": 100 * float(np.trace(matrix)) / total,
        "within_one_pct": 100 * float(matrix[abs(row - col) <= 1].sum()) / total,
        "lower_than_fesm_pct": 100 * float(matrix[row < col].sum()) / total,
        "higher_than_fesm_pct": 100 * float(matrix[row > col].sum()) / total,
    }


def write_confusion(path: Path, matrix: np.ndarray, classes: list[int]) -> None:
    """CSV with one row per your class and one column per FESM class."""
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["yours \\ fesm", *classes])
        for code, counts in zip(classes, matrix, strict=True):
            writer.writerow([code, *counts.tolist()])


def masked_pct(nbr_map: np.ndarray, inside: np.ndarray) -> float:
    """% of pixels inside the outline with no NBR (cloud, shadow, water or nodata)."""
    return 100 * float(np.isnan(nbr_map[inside]).mean())


def at_most(value: float, limit: float) -> dict[str, Any]:
    return {"value": round(value, 2), "limit": limit, "passed": value <= limit}


def gap(days: int, limit: int) -> dict[str, Any]:
    """A scene must fall outside the fire (at least 1 day) and within `limit` days of it."""
    return {"value": days, "limit": limit, "passed": 1 <= days <= limit}


def qa_checks(
    config: dict[str, Any],
    work: Path,
    pre: np.ndarray,
    post: np.ndarray,
    fesm: np.ndarray,
    inside: np.ndarray,
) -> dict[str, dict[str, Any]]:
    """Each check: its value, its limit from config.qa, and whether it passed."""
    qa, fire, scenes = config["qa"], config["fire"], config["scenes"]
    # Every grid prepare.sh wrote must share CRS, pixel edges and size, or pixels don't match.
    grids = set()
    for path in sorted(work.glob("*.tif")):
        _, p = read(path)
        grids.add((str(p["crs"]), tuple(p["transform"]), p["width"], p["height"]))
    fesm_nodata = 100 * float((fesm[inside] == config["fesm"]["nodata"]).mean())
    return {
        "pre_masked_pct": at_most(masked_pct(pre, inside), qa["max_masked_pct"]),
        "post_masked_pct": at_most(masked_pct(post, inside), qa["max_masked_pct"]),
        "pre_gap_days": gap((fire["start_date"] - scenes["pre"]["date"]).days, qa["max_gap_days"]),
        "post_gap_days": gap((scenes["post"]["date"] - fire["end_date"]).days, qa["max_gap_days"]),
        "fesm_nodata_pct": at_most(fesm_nodata, qa["max_fesm_nodata_pct"]),
        "grids_aligned": {"value": len(grids), "limit": 1, "passed": len(grids) == 1},
    }


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):  # 1 MB at a time
            digest.update(chunk)
    return digest.hexdigest()


def command_output(*args: str) -> str:
    return subprocess.run(args, capture_output=True, text=True, check=True).stdout.strip()


def provenance() -> dict[str, Any]:
    """When and with what this run was made, so a result can be traced and repeated."""
    return {
        "utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "git_commit": command_output("git", "rev-parse", "HEAD"),
        # Uncommitted changes mean the commit alone can't reproduce this run.
        "git_dirty": command_output("git", "status", "--porcelain") != "",
        "python": platform.python_version(),
        "packages": {name: version(name) for name in ("numpy", "rasterio", "pyyaml")},
        # Two GDALs: the command-line one made the grids, rasterio's own read and wrote them.
        "gdal_cli": command_output("gdalinfo", "--version"),
        "gdal_rasterio": rasterio.__gdal_version__,
    }


def write(path: Path, array: np.ndarray, profile: dict[str, Any], nodata: float) -> None:
    """Write one band on the same grid as `profile`, with this array's dtype."""
    profile = {**profile, "dtype": array.dtype.name, "nodata": nodata, "count": 1}
    profile.update(driver="GTiff", compress="deflate")
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(array, 1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", type=Path, default=Path("config.yaml"))
    args = parser.parse_args()

    config = load_config(args.config)
    out = Path(config["outputs"]["root"]) / config["fire"]["id"]
    work = out / "work"
    prepare(config, work)

    _, profile = read(work / "pre_nir.tif")  # the shared grid, for writing outputs
    pre = masked_nbr(work, "pre", config)
    post = masked_nbr(work, "post", config)
    dnbr = pre - post
    write(out / "dnbr.tif", dnbr.astype("float32"), profile, nodata=np.nan)

    severity = config["severity"]
    severity_map = classify(dnbr, severity["thresholds"], severity["classes"])
    write(out / "severity.tif", severity_map, profile, nodata=SEVERITY_NODATA)

    fesm, _ = read(work / "fesm.tif")
    matrix = confusion(severity_map, fesm, severity["classes"])
    write_confusion(out / "confusion.csv", matrix, severity["classes"])
    stats = agreement(matrix)

    outline, _ = read(work / "outline.tif")
    inside = outline == 1
    checks = qa_checks(config, work, pre, post, fesm, inside)
    passed = all(c["passed"] for c in checks.values())

    valid = dnbr[~np.isnan(dnbr)]
    metadata = {
        "fire": config["fire"]["id"],
        # If any QA check failed, the agreement numbers are kept but flagged as unreliable.
        "reliable": passed,
        "qa": checks,
        "results": {
            "agreement": stats,
            "dnbr_median": round(float(np.median(valid)), 3),
            "dnbr_valid_pixels": int(valid.size),
            "fesm_grassland_pixels_dropped": int(((fesm == 1) & inside).sum()),
        },
        "inputs": {
            "config": {"path": str(args.config), "sha256": sha256(args.config)},
            "fesm": {
                "path": config["inputs"]["fesm"],
                "sha256": sha256(Path(config["inputs"]["fesm"])),
            },
            "outline": {
                "path": config["inputs"]["outline"],
                "sha256": sha256(Path(config["inputs"]["outline"])),
            },
            "scenes": config["scenes"],
        },
        "settings": {key: config[key] for key in ("grid", "bands", "fesm", "severity", "qa")},
        "run": provenance(),
    }
    # default=str writes dates as "2023-12-07".
    (out / "metadata.json").write_text(json.dumps(metadata, indent=2, default=str) + "\n")

    print(f"dNBR: {valid.size} valid pixels, median {np.median(valid):.2f}")
    print(
        f"Agreement with FESM over {stats['pixels']} pixels: "
        f"{stats['exact_pct']:.1f}% exact, {stats['within_one_pct']:.1f}% within one class; "
        f"lower than FESM {stats['lower_than_fesm_pct']:.1f}%, "
        f"higher {stats['higher_than_fesm_pct']:.1f}%"
    )
    for name, c in checks.items():
        print(
            f"  QA {'PASS' if c['passed'] else 'FAIL'}  {name}: {c['value']} (limit {c['limit']})"
        )
    if not passed:
        print("WARNING: a QA check failed; results are marked unreliable in metadata.json")
    print(f"Wrote dnbr.tif, severity.tif, confusion.csv and metadata.json in {out}")


if __name__ == "__main__":
    main()
