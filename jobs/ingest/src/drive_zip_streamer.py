import io
import struct
import zipfile
from dataclasses import dataclass
from typing import Iterator

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".gif", ".webp", ".tiff", ".tif", ".bmp"}
SIDECAR_EXTENSIONS = {".json"}

# Minimum size of End of Central Directory record
EOCD_SIZE = 22
EOCD_SIGNATURE = b"PK\x05\x06"


@dataclass
class ZipEntry:
    name: str
    _streamer: "DriveZipStreamer"
    _header_offset: int
    _compress_size: int
    _file_size: int
    _compress_type: int

    @property
    def is_image(self) -> bool:
        ext = "." + self.name.rsplit(".", 1)[-1].lower() if "." in self.name else ""
        return ext in IMAGE_EXTENSIONS

    @property
    def is_sidecar(self) -> bool:
        ext = "." + self.name.rsplit(".", 1)[-1].lower() if "." in self.name else ""
        return ext in SIDECAR_EXTENSIONS

    def read(self) -> bytes:
        return self._streamer._read_entry_bytes(self)


class DriveZipStreamer:
    def __init__(self, http_client, file_id: str):
        self._http = http_client
        self._file_id = file_id
        self._file_size: int | None = None
        self._download_url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"

    def _get_file_size(self) -> int:
        if self._file_size is None:
            resp = self._http.get(self._download_url, headers={"Range": "bytes=0-0"})
            content_length = resp.headers.get("Content-Length")
            if content_length:
                self._file_size = int(content_length)
            else:
                # Fallback: read Content-Range
                cr = resp.headers.get("Content-Range", "")
                self._file_size = int(cr.split("/")[-1])
        return self._file_size

    def _range_read(self, start: int, end: int) -> bytes:
        resp = self._http.get(self._download_url, headers={"Range": f"bytes={start}-{end}"})
        return resp.content

    def _find_eocd(self, file_size: int) -> tuple[int, bytes]:
        # Read last 64KB to handle ZIP comments
        search_size = min(65536 + EOCD_SIZE, file_size)
        tail = self._range_read(file_size - search_size, file_size - 1)
        pos = tail.rfind(EOCD_SIGNATURE)
        if pos == -1:
            raise ValueError("End of Central Directory record not found — not a valid ZIP")
        eocd_offset = file_size - search_size + pos
        return eocd_offset, tail[pos:]

    def list_entries(self) -> Iterator[ZipEntry]:
        file_size = self._get_file_size()
        eocd_offset, eocd_data = self._find_eocd(file_size)

        # Parse EOCD: offset 16 = CD offset, offset 12 = CD size
        cd_size = struct.unpack_from("<I", eocd_data, 12)[0]
        cd_offset = struct.unpack_from("<I", eocd_data, 16)[0]

        cd_bytes = self._range_read(cd_offset, cd_offset + cd_size - 1)
        buf = io.BytesIO(cd_bytes)

        CD_SIGNATURE = b"PK\x01\x02"
        while True:
            sig = buf.read(4)
            if sig != CD_SIGNATURE:
                break

            buf.read(2)  # version made by
            buf.read(2)  # version needed
            buf.read(2)  # flags
            compress_type = struct.unpack("<H", buf.read(2))[0]
            buf.read(2)  # mod time
            buf.read(2)  # mod date
            buf.read(4)  # crc32
            compress_size = struct.unpack("<I", buf.read(4))[0]
            file_size_entry = struct.unpack("<I", buf.read(4))[0]
            fname_len = struct.unpack("<H", buf.read(2))[0]
            extra_len = struct.unpack("<H", buf.read(2))[0]
            comment_len = struct.unpack("<H", buf.read(2))[0]
            buf.read(2)  # disk number start
            buf.read(2)  # internal attrs
            buf.read(4)  # external attrs
            header_offset = struct.unpack("<I", buf.read(4))[0]
            fname = buf.read(fname_len).decode("utf-8", errors="replace")
            buf.read(extra_len + comment_len)

            if fname.endswith("/"):
                continue  # directory entry

            yield ZipEntry(
                name=fname,
                _streamer=self,
                _header_offset=header_offset,
                _compress_size=compress_size,
                _file_size=file_size_entry,
                _compress_type=compress_type,
            )

    def _read_entry_bytes(self, entry: ZipEntry) -> bytes:
        # Read local file header to find data offset
        lh = self._range_read(entry._header_offset, entry._header_offset + 29)
        fname_len = struct.unpack_from("<H", lh, 26)[0]
        extra_len = struct.unpack_from("<H", lh, 28)[0]
        data_offset = entry._header_offset + 30 + fname_len + extra_len

        compressed = self._range_read(data_offset, data_offset + entry._compress_size - 1)

        if entry._compress_type == zipfile.ZIP_STORED:
            return compressed
        elif entry._compress_type == zipfile.ZIP_DEFLATED:
            import zlib
            return zlib.decompress(compressed, -15)
        else:
            raise ValueError(f"Unsupported compression type: {entry._compress_type}")
