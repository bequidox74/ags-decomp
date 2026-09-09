meta:
  id: ags_compiled_script
  title: AGS Compiled Script
  application: Adventure Game Studio v3.6.0.55
  endian: le
  encoding: UTF-8

seq:
  - id: magic1
    contents: SCOM
  - id: scom_version
    type: u4
  - id: len_gdata
    type: u4
  - id: num_codes
    type: u4
  - id: len_strings
    type: u4
  - id: gdata
    size: len_gdata
  - id: code
    type: s4
    repeat: expr
    repeat-expr: num_codes
  - id: strings
    type: strings
    size: len_strings
  - id: num_fixups
    type: u4
  - id: fixup_types
    type: u1
    enum: fixup_type
    repeat: expr
    repeat-expr: num_fixups
  - id: fixups
    type: u4
    repeat: expr
    repeat-expr: num_fixups
  - id: num_imports
    type: u4
  - id: imports
    type: str
    terminator: 0
    repeat: expr
    repeat-expr: num_imports
  - id: num_exports
    type: u4
  - id: exports
    type: export
    repeat: expr
    repeat-expr: num_exports
  - id: num_sections
    type: u4
  - id: sections
    type: section
    repeat: expr
    repeat-expr: num_sections
  - id: magic2
    contents: [0xfe, 0xca, 0xef, 0xbe]

types:
  strings:
    seq:
      - id: string
        type: str
        terminator: 0
        repeat: eos
  export:
    seq:
      - id: name
        type: str
        terminator: 0
      - id: addr_raw
        type: u4
    instances:
      addr:
        value: addr_raw & 0x00ffffff
      etype:
        value: (addr_raw >> 24) & 0xff
        enum: export_type
  section:
    seq:
      - id: name
        type: str
        terminator: 0
      - id: offset
        type: u4

enums:
  fixup_type:
    1: global_data
    2: function
    3: string
    4: import
    5: data_data
    6: stack
  export_type:
    1: function
    2: data

