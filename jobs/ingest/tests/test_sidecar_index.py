"""
Tests for SidecarIndex: finding a media file's Sidecar by the names Takeout gives Sidecars.
"""
import pytest

from src.sidecar_index import SidecarIndex

FOLDER = "Takeout/Google Photos/Photos from 2024"


def _find(media_name: str, sidecar_names: list[str]) -> str | None:
    """The name of the Sidecar found for `media_name`, all files in one folder."""
    index = SidecarIndex({f"{FOLDER}/{name}": name.encode() for name in sidecar_names})
    sidecar = index.find(f"{FOLDER}/{media_name}")
    return sidecar.decode() if sidecar is not None else None


@pytest.mark.parametrize("sidecar_name", [
    "IMG_1.jpg.json",
    "IMG_1.jpg.supplemental-metadata.json",
    "IMG_1.jpg.supplemental-meta.json",
    "IMG_1.jpg.s.json",
    "IMG_1.jpg..json",
])
def test_finds_the_sidecar_by_each_naming_takeout_uses(sidecar_name):
    assert _find("IMG_1.jpg", [sidecar_name]) == sidecar_name


def test_matching_ignores_case():
    assert _find("VID_0001.mov", ["VID_0001.MOV.json"]) == "VID_0001.MOV.json"


@pytest.mark.parametrize("original, duplicate", [
    ("IMG_1.jpg.json", "IMG_1.jpg(1).json"),
    ("IMG_1.jpg.supplemental-metadata.json", "IMG_1.jpg.supplemental-metadata(1).json"),
])
def test_a_duplicate_and_its_original_each_get_their_own_sidecar(original, duplicate):
    # Listing the duplicate's Sidecar first: it also starts with "IMG_1.jpg".
    assert _find("IMG_1.jpg", [duplicate, original]) == original
    assert _find("IMG_1(1).jpg", [duplicate, original]) == duplicate


def test_a_duplicate_does_not_take_its_originals_sidecar():
    assert _find("IMG_1(2).jpg", ["IMG_1.jpg.json", "IMG_1.jpg(1).json"]) is None


def test_a_name_that_really_ends_in_a_counter_finds_its_sidecar():
    assert _find("scan(3).jpg", ["scan(3).jpg.supplemental-metadata.json"]) == "scan(3).jpg.supplemental-metadata.json"


def test_finds_the_sidecar_of_a_long_name_cut_to_takeouts_limit():
    media = "PXL_20240612_182549759.NIGHT.PORTRAIT-01.COVER.jpg"  # 50 characters
    sidecar = media[:46] + ".json"
    assert len(sidecar) == 51
    assert _find(media, [sidecar]) == sidecar


def test_finds_the_sidecar_of_a_long_duplicate_name():
    media = "PXL_20240612_182549759.NIGHT.PORTRAIT-01.COVER(1).jpg"
    sidecar = "PXL_20240612_182549759.NIGHT.PORTRAIT-01.COVER.jpg"[:46] + "(1).json"
    assert _find(media, [sidecar]) == sidecar


def test_two_different_sidecars_for_one_name_match_neither():
    # Indexing a file under another file's metadata is worse than leaving it unmatched.
    index = SidecarIndex({
        f"{FOLDER}/IMG_1.jpg.json": b"one",
        f"{FOLDER}/IMG_1.jpg.supplemental-metadata.json": b"other",
    })
    assert index.find(f"{FOLDER}/IMG_1.jpg") is None


def test_a_sidecar_in_another_folder_is_not_matched():
    index = SidecarIndex({"Takeout/Google Photos/Photos from 2019/IMG_1.jpg.json": b"2019"})
    assert index.find("Takeout/Google Photos/Photos from 2024/IMG_1.jpg") is None


def test_same_named_files_in_different_folders_get_their_own_sidecars():
    index = SidecarIndex({
        "Takeout/Google Photos/Photos from 2019/IMG_1.jpg.json": b"2019",
        "Takeout/Google Photos/Photos from 2024/IMG_1.jpg.json": b"2024",
    })
    assert index.find("Takeout/Google Photos/Photos from 2019/IMG_1.jpg") == b"2019"
    assert index.find("Takeout/Google Photos/Photos from 2024/IMG_1.jpg") == b"2024"


def test_a_media_file_without_a_sidecar_finds_none():
    assert _find("IMG_2.jpg", ["IMG_1.jpg.json", "IMG_20.jpg.json"]) is None
