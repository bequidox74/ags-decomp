meta:
  id: ags_game_data
  title: AGS Main Game Data File
  application: Adventure Game Studio v3.6.0.55
  file-extension: dta
  license: CC0-1.0
  imports:
    - ags_compiled_script
    - ags_view
    - ags_character
  encoding: UTF-8
  endian: le
  bit-endian: be

seq:
  - id: signature
    contents: Adventure Creator Game File v2
  - id: game_data_version
    type: s4
  - id: editor_version_length
    type: s4
  - id: editor_version
    type: str
    size: editor_version_length
  - id: extended_engine_caps
    type: s4
  - id: game_setup
    type: game_setup
  - id: guid_string
    type: str
    size: 40
  - id: save_game_file_extension
    type: str
    size: 20
  - id: save_game_folder_name
    type: str
    size: 50
  - id: fonts
    type: font
    repeat: expr
    repeat-expr: game_setup.font_count
  - id: topmost_sprite_raw
    type: s4
  - id: sprite_flags
    type: sprite_flags
    repeat: expr
    repeat-expr: topmost_sprite_raw
  - size: 68 # pad/align? src doc says "inventory item slot 0 is unused"
  - id: inventory_items
    type: inventory_item
    repeat: expr
    repeat-expr: game_setup.inventory_item_count
  - id: cursors
    type: cursor
    repeat: expr
    repeat-expr: game_setup.cursor_count
  - id: char_interact_scripts
    type: interaction_scripts
    repeat: expr
    repeat-expr: game_setup.num_characters
  - id: inv_item_interact_scripts
    type: interaction_scripts
    repeat: expr
    repeat-expr: game_setup.inventory_item_count
  - id: num_parser_words
    type: s4
  - id: parser_words
    type: parser_word
    repeat: expr
    repeat-expr: num_parser_words
  - id: global_script
    type: ags_compiled_script
  - id: dialog_scripts
    type: ags_compiled_script
  - id: num_scripts
    type: s4
  - id: scripts
    type: ags_compiled_script
    repeat: expr
    repeat-expr: num_scripts
  - id: views
    type: ags_view
    repeat: expr
    repeat-expr: game_setup.num_views
  - id: characters
    type: ags_character
    repeat: expr
    repeat-expr: game_setup.num_characters

types:
  game_setup:
    seq:
      - id: game_name
        type: str
        size: 50
      - id: game_name_padding
        size: 2
      - id: options
        type: u4
        repeat: expr
        repeat-expr: 100
      - id: palette_types
        type: s1
        enum: palette_type
        repeat: expr
        repeat-expr: 256
      - id: palette_colorfs
        type: palette_color
        repeat: expr
        repeat-expr: 256
      - id: num_views
        type: s4
      - id: num_characters
        type: s4
      - id: player_character_id
        type: s4
      - id: maximum_score
        type: s4
      - id: inv_items_count_raw
        type: s2
      - id: item_count_padding
        size: 2
      - id: dialog_count
        type: s4
      - id: numdlgmessage
        type: s4
      - id: font_count
        type: s4
      - id: color_depth
        type: s4
      - id: target_win
        type: s4
      - id: dialog_options_bullet
        type: s4
      - id: hotspot_dot_color
        -orig-id: hotdot
        type: s2
      - id: hotspot_crosshair_color
        -orig-id: hotdotouter
        type: s2
      - id: game_unique_id
        type: s4
      - id: gui_count
        type: s4
      - id: cursor_count
        type: s4
      - id: game_resolution_type
        type: s4
        enum: game_resolution_type
      - id: game_resolution
        type: game_resolution
        if: game_resolution_type == game_resolution_type::custom
      - id: lipsync_default_frame
        type: s4
      - id: inventory_hotspot_marker_image
        type: s4
      - id: reserved
        size: 17 * 4
      - id: has_game_message
        type: s4
        repeat: expr
        repeat-expr: 500
        doc-ref: "Common/ac/gamesetupstructbase.cpp: GameSetupStructBase::ReadFromFile"
      - id: load_dictionary
        type: s4
      - id: globalscript_not_null
        type: s4
      - id: chars_not_null
        type: s4
      - id: compiled_script_not_null
        type: s4

    enums:
      palette_type:
        0: pal_gamewide
        2: pal_background
      game_resolution_type:
        "-1": undefined
        0: default
        1: r320x200
        2: r320x240
        3: r640x400
        4: r640x480
        5: r800x600
        6: r1024x768
        7: r1280x720
        8: custom

    instances:
      inventory_item_count:
        value: inv_items_count_raw - 1

    types:
      palette_color:
        seq:
          - id: r_raw
            type: s1
          - id: g_raw
            type: s1
          - id: b_raw
            type: s1
          - id: filler
            type: s1
        instances:
          r:
            value: r_raw * 4
          g:
            value: g_raw * 4
          b:
            value: b_raw * 4
      game_resolution:
        seq:
          - id: width
            type: u4
          - id: height
            type: u4

  font:
    seq:
      - id: flags
        type: s4
      - id: size_multiplier
        type: s4
      - id: outline
        type: s4
      - id: vertical_offset
        type: s4
      - id: line_spacing
        type: s4
    instances:
      flag_size_multiplier:
        value: (flags >> 0) & 1 == 1
      flag_line_spacing:
        value: (flags >> 1) & 1 == 1
      flag_nominal_height:
        value: (flags >> 2) & 1 == 1
      flag_ascender_fixup:
        value: (flags >> 3) & 1 == 1
      flag_logical_custom_height:
        value: (flags >> 4) & 1 == 1

  sprite_flags:
    seq:
      - id: flags
        type: s1
    instances:
      flag_hires:
        value: (flags >> 0) & 1 == 1
      flag_hicolor:
        value: (flags >> 1) & 1 == 1
      flag_dynamicalloc:
        value: (flags >> 2) & 1 == 1
      flag_truecolor:
        value: (flags >> 3) & 1 == 1
      flag_alphachannel:
        value: (flags >> 4) & 1 == 1
      flag_var_resolution:
        value: (flags >> 5) & 1 == 1

  inventory_item:
    seq:
      - id: description
        type: str
        size: 25
        terminator: 0
      - id: desc_padding
        size: 3
      - id: image
        type: s4
      - id: cursor_image
        type: s4
      - id: hotspot_x
        type: s4
      - id: hotspot_y
        type: s4
      - id: reserved
        size: 5 * 4 # 5 integers
      - id: player_starts_with
        type: s1
      - id: end_padding
        size: 3

  cursor:
    seq:
      - id: image
        type: s4
      - id: hotspot_x
        type: s2
      - id: hotspot_y
        type: s2
      - id: num_views
        type: s2
      - id: name
        type: str
        size: 10
        terminator: 0
      - id: flags
        type: s1
      - id: padding
        size: 3

  interaction_scripts:
    seq:
      - id: num_scripts
        type: s4
      - id: script_names
        type: str
        terminator: 0
        repeat: expr
        repeat-expr: num_scripts

  parser_word:
    seq:
      - id: size
        type: s4
      - id: encrypted # enc[i] = src[i] + "Avis Durgan"[i % len(key)]
        type: str
        size: size
      - id: word_group
        type: s2

instances:
  topmost_sprite:
    value: topmost_sprite_raw - 1
