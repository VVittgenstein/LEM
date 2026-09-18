"""Build with an existing C++17 toolchain and pinned raylib 5.5."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import urllib.request
import zipfile

RAYLIB_COMMIT = "c1ab645ca298a2801097931d1079b10ff7eb9df8"
RAYLIB_ARCHIVE_SHA256 = "aacb13c34e996e86267223f64f8631ed0b408e9b5dc234d8a844d7a5a97a26dc"
ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "viewer/build"

def find_cmake() -> str:
    if found := shutil.which("cmake"):
        return found
    if os.name == "nt":
        vswhere = Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "Microsoft Visual Studio/Installer/vswhere.exe"
        if vswhere.is_file():
            installs = json.loads(subprocess.check_output([str(vswhere), "-products", "*", "-format", "json"], text=True, encoding="utf-8"))
            for install in reversed(installs):
                candidate = Path(install["installationPath"]) / "Common7/IDE/CommonExtensions/Microsoft/CMake/CMake/bin/cmake.exe"
                if candidate.is_file():
                    return str(candidate)
    raise RuntimeError("CMake 3.20+ and a C++17 compiler are required.")

def raylib_source(cache: Path | None) -> Path:
    target = BUILD / "_deps" / f"raylib-{RAYLIB_COMMIT}"
    if (target / "src/raylib.h").is_file():
        return target
    if cache is None:
        raise RuntimeError("Provide --raylib-source PATH, or --download-cache PATH for the pinned raylib archive.")
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / f"raylib-{RAYLIB_COMMIT}.zip"
    if not archive.is_file():
        print(f"Downloading pinned raylib 5.5 to {archive}", flush=True)
        with urllib.request.urlopen(f"https://codeload.github.com/raysan5/raylib/zip/{RAYLIB_COMMIT}", timeout=90) as response:
            content = response.read()
        archive.write_bytes(content)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    if digest != RAYLIB_ARCHIVE_SHA256:
        raise ValueError(f"Pinned raylib archive checksum mismatch: {archive}")
    with zipfile.ZipFile(archive) as bundle:
        parent = target.parent.resolve()
        for item in bundle.infolist():
            if not (parent / item.filename).resolve().is_relative_to(parent):
                raise ValueError("Unexpected archive path")
        bundle.extractall(parent)
    (target.parent / "raylib-source.json").write_text(json.dumps({"commit": RAYLIB_COMMIT, "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest()}, indent=2), encoding="utf-8")
    return target

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raylib-source", type=Path)
    parser.add_argument("--download-cache", type=Path)
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()
    cmake = find_cmake()
    source = args.raylib_source or raylib_source(args.download_cache)
    command = [cmake, "-S", str(ROOT / "viewer/lem_viewer/voxel/native"), "-B", str(BUILD / "native"), f"-DLEM_RAYLIB_SOURCE={source.resolve()}"]
    if os.name == "nt":
        command += ["-G", "Visual Studio 17 2022", "-A", "x64"]
    subprocess.run(command, check=True)
    subprocess.run([cmake, "--build", str(BUILD / "native"), "--config", "Release", "--parallel", "4"], check=True)
    if args.test:
        ctest = str(Path(cmake).with_name("ctest.exe" if os.name == "nt" else "ctest"))
        subprocess.run([ctest, "--test-dir", str(BUILD / "native"), "-C", "Release", "--output-on-failure"], check=True)

if __name__ == "__main__":
    main()
