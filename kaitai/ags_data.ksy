meta:
  # AGS source code repo: https://github.com/adventuregamestudio/ags
  # Data File Format taken from DataFileWriter.cs
  id: ags_data
  title: AGS Data File
  application: Adventure Game Studio
  file-extension: data
  license: CC0-1.0
  encoding: UTF-8
  endian: le
seq:
  - id: clib_begin_signature
    contents: "CLIB\x1A"
  - id: clib_version
    type: s1
  - id: data_file_index
    type: s1
  - id: header
    type: clib_header
    if: data_file_index == 0
types:
  clib_header:
    seq:
      - id: reserved_options
        type: s4
      - id: data_file_count
        type: s4
      - id: data_file_names
        type: str
        terminator: 0
        repeat: expr
        repeat-expr: data_file_count
      - id: file_count
        type: s4
      - id: files
        type: file
        repeat: expr
        repeat-expr: file_count
      # CLIB end signature does not appear in AGS v3.6.0 in standalone data files.
  file:
    seq:
      - id: name
        type: str
        terminator: 0
      - id: data_file_index
        type: s1
      - id: offset
        type: s8
      - id: length
        type: s8
    instances:
      body:
        pos: offset
        size: length
