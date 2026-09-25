meta:
  id: ags_dialog
  file-extension: ags_dialog
  encoding: utf-8
  endian: le

seq:
  - id: options
    type: str
    size: 150
    repeat: expr
    repeat-expr: 30
  - id: flags
    type: flag
    repeat: expr
    repeat-expr: 30
  - id: option_scripts
    size: 4
  - id: entry_points
    type: u2
    repeat: expr
    repeat-expr: 30
  - id: startup_entry_point
    type: u2
  - id: code_size
    type: u2
  - id: num_options
    type: u4
  - id: show_text_parser_raw
    type: u4

instances:
  show_text_parser:
    value: show_text_parser_raw != 0
    
types:
  flag:
    seq:
      - id: flag
        type: u4
    instances:
      on:
        value: (flag >> 0) & 0x1 != 0
      off_perm:
        value: (flag >> 1) & 0x1 != 0
      norepeat:
        value: (flag >> 3) & 0x1 != 0
      has_been_chosen:
        value: (flag >> 4) & 0x1 != 0
