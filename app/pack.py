"""Turn releases shipped as loose images (one folder per volume) into one CBZ per volume.

Kavita files loose images under a separate series, so a series mixing CBZ packs and image folders shows up
twice. Lire packs the images next to the other volumes and its Kavita libraries skip loose images entirely;
the original files stay where they are so the torrent keeps seeding.
"""
import re
import zipfile
from pathlib import Path

from parse import parse_volumes

IMAGES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif", ".bmp"}
ARCHIVES = {".cbz", ".cbr", ".cb7", ".zip", ".rar", ".7z", ".pdf", ".epub"}


def natural_key(path: Path):
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", path.name)]


def image_dirs(root: Path):
    """Folders holding images and no archive, with their images in reading order."""
    if not root.is_dir():
        return
    for folder in [root, *sorted((d for d in root.rglob("*") if d.is_dir()), key=natural_key)]:
        files = [f for f in folder.iterdir() if f.is_file()]
        images = [f for f in files if f.suffix.lower() in IMAGES]
        if images and not any(f.suffix.lower() in ARCHIVES for f in files):
            yield folder, sorted(images, key=natural_key)


def volume_of(name: str):
    """Single volume number named by a folder ('Tome 64', 'T07', '12'); None for chapters or ranges."""
    volumes, chapters_only, _ = parse_volumes(name)
    if chapters_only:
        return None
    if len(volumes) == 1:
        return next(iter(volumes))
    if volumes:
        return None
    match = re.fullmatch(r"\D*?0*(\d{1,3})\D*", name)
    return int(match.group(1)) if match else None


def pack_images(content: Path, series_dir: Path, series: str) -> list[str]:
    """Write '<series> T<nn>.cbz' for every image folder naming one volume the series has no archive for yet."""
    have = set()
    for archive in series_dir.rglob("*"):
        if archive.is_file() and archive.suffix.lower() in ARCHIVES:
            have |= parse_volumes(archive.stem)[0]
    made = []
    for folder, images in image_dirs(content):
        volume = volume_of(folder.name)
        if volume is None or volume in have:
            continue
        target = series_dir / f"{series} T{volume:02d}.cbz"
        partial = target.with_name(target.name + ".part")
        with zipfile.ZipFile(partial, "w", zipfile.ZIP_STORED) as archive:
            for index, image in enumerate(images, 1):
                archive.write(image, f"{index:04d}{image.suffix.lower()}")
        partial.replace(target)
        have.add(volume)
        made.append(target.name)
    return made
