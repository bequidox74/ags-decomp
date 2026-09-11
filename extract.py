import os
from pathlib import Path
from typing import NamedTuple

from binary_reader import BinaryReader, Source
from utils import verify

CLIB_START_SIG = b"CLIB\x1a"

SCOM_START_SIG = b"SCOM"
SCOM_END_SIG = b"\xfe\xca\xef\xbe"  # 0xBEEFCAFE in BE


class FileInfo(NamedTuple):
    name: str
    offset: int
    length: int


def read_script_info(data_file: Source) -> list[FileInfo]:
    br = BinaryReader(data_file)
    sig = br.read(len(CLIB_START_SIG))
    verify(sig == CLIB_START_SIG, "Multi-file setup is not supported.")
    br.skip(1)  # version
    file_index = br.u8()
    verify(file_index == 0)
    br.skip(4)  # reserved options

    df_count = br.u32()
    verify(df_count == 1, "Multi-file setup is not supported.")
    for _ in range(df_count):
        br.cstr()  # ignore these

    fcount = br.u32()
    file_infos: list[FileInfo] = []
    for _ in range(fcount):
        name = br.cstr()
        df_index = br.u8()
        verify(df_index == 0)
        offset = br.u64()
        length = br.u64()
        finfo = FileInfo(name, offset, length)
        file_infos.append(finfo)

    return file_infos


# TODO: proper parsing and extraction of assets
def extract_scripts(
    data_file: Source,
    out_dir: Path,
    verify_version: int | None = 90,
    extension: str = ".o",
    max_count: int | None = None,
) -> list[Path]:
    os.makedirs(out_dir, exist_ok=True)
    with BinaryReader(data_file) as br:
        return _extract_scripts(br, out_dir, verify_version, extension, max_count)


def _extract_scripts(
    br: BinaryReader,
    out_dir: Path,
    verify_version: int | None,
    extension: str,
    max_count: int | None,
) -> list[Path]:
    out: list[Path] = []
    i = 1
    while (start := br.find(SCOM_START_SIG)) > 0:
        end = br.find(SCOM_END_SIG, start + len(SCOM_START_SIG)) + len(SCOM_END_SIG)
        if end < 0:
            raise RuntimeError("End signature not found for script at 0x{sig:X}.")

        br.seek(start)
        script = br.read(end - start)
        if verify_version is not None:
            br.seek(start + len(SCOM_START_SIG))
            version = br.u32()
            verify(version == verify_version)
        out_file = out_dir / f"script{i}{extension}"
        out.append(out_file)
        with open(out_file, "wb") as handle:
            handle.write(script)
        if max_count is not None and i >= max_count:
            return out
        i += 1

    return out
