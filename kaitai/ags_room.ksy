meta:
  id: ags_room
  file-extension: crm
  application: Adventure Game Studio
  imports: ags_compiled_script
  encoding: UTF-8
  endian: le

seq:
  - id: data_version
    type: u2
  - id: main_block
    type: block
  - id: script_block
    type: block
  - id: obj_names_block
    type: block
  - id: obj_scr_names_block
    type: block
  - id: anim_bg_block
    type: block
  - id: proprs_block
    type: block
  - id: magic
    contents: [255]

types:
  block:
    seq:
      - id: type
        type: u1
      - id: id
        type: strz
        size: 16
        if: type == 0
      - id: size
        type: u8
      - id: body
        size: size
        type:
          switch-on: type
          cases:
            0: named_block
            1: main_block
            5: obj_names_block
            6: anim_bg_block
            7: script_block
            8: properties_block
            9: obj_scr_names_block

  main_block:
    seq:
      - id: background_bpp
        type: u4
      - id: num_walk_behinds
        type: u2
      - id: walk_behind_baselines
        type: s2
        repeat: expr
        repeat-expr: num_walk_behinds
      - id: num_hotspots
        type: u4
      - id: hotspot_walktos
        type: hotspot_walkto
        repeat: expr
        repeat-expr: num_hotspots
      - id: hspot_names
        type: string
        repeat: expr
        repeat-expr: num_hotspots
      - id: hspot_script_names
        type: string
        repeat: expr
        repeat-expr: num_hotspots
      - id: poly_point_areas # legacy
        type: u4
      - id: top_edge
        type: s2
      - id: bottom_edge
        type: s2
      - id: left_edge
        type: s2
      - id: right_edge
        type: s2
      - id: num_objects
        type: u2
      - id: objects
        type: room_object
        repeat: expr
        repeat-expr: num_objects
      - id: interaction_vars
        type: s4
      - id: num_room_regions
        type: u4
      - id: event_handlers
        type: interaction_scripts
      - id: hotspot_handlers
        type: interaction_scripts
        repeat: expr
        repeat-expr: num_hotspots
      - id: object_handlers
        type: interaction_scripts
        repeat: expr
        repeat-expr: num_objects
      - id: region_handlers
        type: interaction_scripts
        repeat: expr
        repeat-expr: num_room_regions
      - id: object_baselines
        type: s4
        repeat: expr
        repeat-expr: num_objects
      - id: width
        type: u2
      - id: height
        type: u2
      - id: object_flags
        type: u2
        repeat: expr
        repeat-expr: num_objects
      - id: mask_resolution
        type: u2
      - id: num_walk_areas
        type: u4
      - id: walk_areas_scaling_far
        type: s2
        repeat: expr
        repeat-expr: num_walk_areas
      - id: walk_areas_player_view
        type: s2
        repeat: expr
        repeat-expr: num_walk_areas
      - id: walk_areas_scaling_near
        type: s2
        repeat: expr
        repeat-expr: num_walk_areas
      - id: walk_areas_top
        type: s2
        repeat: expr
        repeat-expr: num_walk_areas
      - id: walk_areas_bottom
        type: s2
        repeat: expr
        repeat-expr: num_walk_areas
      - id: legacy_room_passwords
        size: 11
      - id: startup_music
        type: u1
      - id: save_load_disabled
        type: u1
      - id: player_char_off
        type: u1
      - id: player_view
        type: u1
      - id: music_volume
        type: u1
      - id: flags
        type: u1
      - id: reserved_options
        size: 4
      - id: num_messages
        type: u2
      - id: game_id
        type: u4
      - id: message_infos
        type: message_info
        repeat: expr
        repeat-expr: num_messages
      - id: encrypted_msgs
        type: strz
        repeat: expr
        repeat-expr: num_messages
      - id: room_anims
        type: u2 # legacy
      - id: wa_player_view_again
        size: 16 * 2
      - id: region_lights
        type: s2
        repeat: expr
        repeat-expr: num_room_regions
      - id: region_tints
        type: s4
        repeat: expr
        repeat-expr: num_room_regions
      - id: bitmap_palette
        type: rgb4
        repeat: expr
        repeat-expr: 256
      - id: bitmap_lzw
        type: lzw_bitmap
      - id: masks
        size-eos: true

  obj_names_block:
    seq:
      - id: num_objects
        type: u1
      - id: names
        type: string
        repeat: expr
        repeat-expr: num_objects

  obj_scr_names_block:
    seq:
      - id: num_objects
        type: u1
      - id: script_names
        type: string
        repeat: expr
        repeat-expr: num_objects

  anim_bg_block:
    seq:
      - id: num_bg_frames
        type: u1
      - id: bg_anim_speed
        type: u1
      - id: is_palette_shared
        type: u1
        repeat: expr
        repeat-expr: num_bg_frames
      - id: bitmaps
        type: lzw_bitmap
        repeat: expr
        repeat-expr: num_bg_frames

  script_block:
    seq:
      - id: script
        type: ags_compiled_script

  properties_block:
    seq:
      - id: block_version
        type: u4
      - id: room_props
        type: values
      - id: other_props # TODO!
        type: values
        size-eos: true
    types:
      values:
        seq:
          - id: props_version
            type: u4
          - id: map
            type: map

  named_block:
    seq:
      - id: contents
        type:
          switch-on: _parent.id
          cases:
            '"ext_sopts"': string_opts_block

  string_opts_block:
    seq:
      - id: str_options
        type: map

  lzw_bitmap:
    seq:
      - id: uncompressed
        type: u4
      - id: compressed
        type: u4
      - id: bitmap
        size: compressed

  string:
    seq:
      - id: size
        type: u4
      - id: str
        type: str
        size: size

  hotspot_walkto:
    seq:
      - id: walkto_x
        type: s2
      - id: walkto_y
        type: s2

  room_object:
    seq:
      - id: sprite
        type: u2
      - id: x
        type: s2
      - id: y
        type: s2
      - id: room
        type: s2
      - id: is_on_raw
        type: u2
    instances:
      is_on:
        value: is_on_raw != 0

  interaction_scripts:
    seq:
      - id: num_funcs
        type: u4
      - id: func_names
        type: str
        terminator: 0
        repeat: expr
        repeat-expr: num_funcs

  message_info:
    seq:
      - id: display_as
        type: u1
      - id: flags
        type: u1

  rgb4:
    seq:
      - id: r
        type: u1
      - id: g
        type: u1
      - id: b
        type: u1
      - id: filler
        size: 1

  map:
    seq:
      - id: map_size
        type: u4
      - id: mappings
        type: mapping
        repeat: expr
        repeat-expr: map_size
    types:
      mapping:
        seq:
          - id: first
            type: string
          - id: second
            type: string
