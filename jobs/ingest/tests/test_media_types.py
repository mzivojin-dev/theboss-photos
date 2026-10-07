import pytest

from src.media_types import content_type_for, extension_of


@pytest.mark.parametrize("filename, extension", [
    ("Takeout/Google Photos/IMG_1.JPG", ".jpg"),
    ("Takeout/Google Photos/IMG_1.jpg.supplemental-metadata.json", ".json"),
    ("Takeout/Google Photos/Trip.2020/README", ""),
    ("README", ""),
])
def test_extension_of_reads_the_extension_of_the_file_name_only(filename, extension):
    assert extension_of(filename) == extension


def test_an_unknown_extension_gets_a_generic_content_type():
    assert content_type_for("notes.txt") == "application/octet-stream"
