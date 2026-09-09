meta:
  id: ags_view
  application: "Adventure Game Studio"
  endian: le

seq:
  - id: num_loops
    type: u2
  - id: loops
    type: loop
    repeat: expr
    repeat-expr: num_loops

types:
  loop:
    seq:
      - id: num_frames
        type: u2
      - id: run_next_loop_raw
        type: u4
      - id: frames
        type: frame
        repeat: expr
        repeat-expr: num_frames
    instances:
      run_next_loop:
        value: run_next_loop_raw == 1
  frame:
    seq:
      - id: image
        type: u4
      - id: x_offset
        type: s2
      - id: y_offset
        type: s2
      - id: alignment
        size: 2
      - id: flipped_raw
        type: u4
      - id: audio_array_id
        type: u4
      - id: reserved
        type: u4
        repeat: expr
        repeat-expr: 2
