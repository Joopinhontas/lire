import io
import sys
import zipfile
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from pack import image_dirs, pack_images, volume_of  # noqa: E402


def jpg(path, shade):
    buf = io.BytesIO()
    Image.new("RGB", (20, 30), (shade, 0, 0)).save(buf, "JPEG")
    path.write_bytes(buf.getvalue())


def test_volume_names():
    assert volume_of("Tome 64") == 64
    assert volume_of("T07") == 7
    assert volume_of("12") == 12
    assert volume_of("Chapitre 120") is None
    assert volume_of("Tomes 61 à 69") is None
    assert volume_of("Bonus") is None


def test_image_folders_become_cbz_once(tmp_path):
    series = tmp_path / "Kingdom"
    raw = series / "Kingdom"
    for tome in ("Tome 64", "Tome 70"):
        (raw / tome).mkdir(parents=True)
        for page in (10, 2, 1):
            jpg(raw / tome / f"p{page}.jpg", page * 10)
    (raw / "Tome 70" / "p3.jpg.!qB").write_bytes(b"partial")
    (series / "Kingdom T61-69").mkdir()
    zipfile.ZipFile(series / "Kingdom T61-69" / "Kingdom T64.cbz", "w").close()

    made = pack_images(raw, series, "Kingdom")
    assert made == ["Kingdom T70.cbz"]
    with zipfile.ZipFile(series / "Kingdom T70.cbz") as cbz:
        assert cbz.namelist() == ["0001.jpg", "0002.jpg", "0003.jpg"]
    assert pack_images(raw, series, "Kingdom") == []
    assert [d.name for d, _ in image_dirs(series / "Kingdom T61-69")] == []
