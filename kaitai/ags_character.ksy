meta:
  id: ags_character
  file-extension: ags_character
  endian: le
  encoding: UTF-8

seq:
  - id: def_view_raw
    type: u4
  - id: talk_view_raw
    type: u4
  - id: view_raw
    type: u4
  - id: starting_room
    type: u4
  - id: prev_room
    type: u4
  - id: x
    type: s4
  - id: y
    type: s4
  - id: flags
    type: u4
  - id: following
    type: u2
  - id: follow_info
    type: u2
  - id: idle_view_raw
    type: u4
  - id: idle_time
    type: s2
  - id: idle_left
    type: s2
  - id: transparency
    type: s2
  - id: baseline
    type: s2
  - id: active_inv
    type: u4
  - id: talk_color
    type: u4
  - id: think_view_raw
    type: u4
  - id: blink_view_raw
    type: u2
  - id: blink_interval
    type: s2
  - id: blink_timer
    type: s2
  - id: blink_frame
    type: u2
  - id: walk_speed_y
    type: s2
  - id: pic_yoffs
    type: s2
  - id: z
    type: s4
  - id: walk_wait
    type: u4
  - id: speech_anim_speed
    type: s2
  - id: idle_anim_speed
    type: s2
  - id: blocking_width
    type: u2
  - id: blocking_height
    type: u2
  - id: index_id
    type: u4
  - id: pic_xoffs
    type: s2
  - id: walk_wait_counter
    type: u2
  - id: loop
    type: u2
  - id: frame
    type: u2
  - id: walking
    type: u2
  - id: animating
    type: u2
  - id: walk_speed
    type: u2
  - id: anim_speed
    type: u2
  - id: starts_with_item_raw
    type: u2
    repeat: expr
    repeat-expr: 301
  - id: act_x
    type: s2
  - id: act_y
    type: s2
  - id: name
    type: str
    size: 40
  - id: script_name
    type: str
    size: 20
  - id: on
    type: u1
  - id: padding
    size: 1

instances:
  def_view:
    value: def_view_raw + 1
  talk_view:
    value: talk_view_raw + 1
  view:
    value: view_raw + 1
  idle_view:
    value: idle_view_raw + 1
  think_view:
    value: think_view_raw + 1
  blink_view:
    value: blink_view_raw + 1
