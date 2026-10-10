"""Download the spec zips from the 3GPP archive and unzip them into data/docx/<name>/."""

import shutil
import urllib.request
import zipfile

from specdelta import config

ARCHIVE_URL = "https://www.3gpp.org/ftp/Specs/archive"


def archive_url(name: str) -> str:
    """URL of a spec zip, e.g. 38300-ib0 -> .../38_series/38.300/38300-ib0.zip"""
    number = name.rsplit("-", 1)[0]  # "38300" or "38101-1"
    spec = f"{number[:2]}.{number[2:]}"
    return f"{ARCHIVE_URL}/{number[:2]}_series/{spec}/{name}.zip"


def download_missing() -> None:
    config.RAW_DIR.mkdir(parents=True, exist_ok=True)
    for name in config.DOCUMENTS:
        if any(config.RAW_DIR.glob(f"{name}.*")):
            continue
        url = archive_url(name)
        print(f"downloading {url}")
        urllib.request.urlretrieve(url, config.RAW_DIR / f"{name}.zip")


def extract_all() -> None:
    """Unzip each raw file into its own folder. Plain .docx files are copied as they are."""
    for name in config.DOCUMENTS:
        target = config.DOCX_DIR / name
        target.mkdir(parents=True, exist_ok=True)
        zip_path = config.RAW_DIR / f"{name}.zip"
        docx_path = config.RAW_DIR / f"{name}.docx"
        if zip_path.exists():
            with zipfile.ZipFile(zip_path) as archive:
                archive.extractall(target)
        elif docx_path.exists():
            shutil.copy(docx_path, target)
        else:
            print(f"missing: {name} (expected {zip_path.name} in {config.RAW_DIR})")
            continue
        print(f"{name}: {', '.join(sorted(p.name for p in target.glob('*.docx')))}")


if __name__ == "__main__":
    download_missing()
    extract_all()
