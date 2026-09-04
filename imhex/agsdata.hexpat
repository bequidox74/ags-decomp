#define MAX_GUID_LENGTH 40
#define MAX_SG_EXT_LENGTH 20
#define MAX_SG_FOLDER_LEN 50
#define MAX_STATIC_SPRITES 90000

import std.string;
import type.color;
import type.guid;

using NullString = std::string::NullString;
using RGBA8 = type::RGBA8;

struct FileEntry {
    NullString assetName;
    u8 dataFileIndex;
    u64 offset;
    u64 length;
};

struct ClibHeader {
    u32 reservedOptions;
    u32 numberOfDataFilenames;
    NullString dataFilenames[numberOfDataFilenames];
    u32 numberOfFiles;
    FileEntry fileEntries[numberOfFiles];
};

enum PaletteColorType : u8 {
    Background = 2,
    Gamewide = 0,
};

struct Palette {
    PaletteColorType pallete[256];
    RGBA8 colors[256];
};

struct GameSetup {
    char gameName[50];
    padding[2];
    u32 options[100];
    Palette palette;
    u32 viewCount;
    u32 characterCount;
    u32 playerId;
    u32 maximumScore;
    u16 inventoryItemCount;
    padding[2];
    u32 dialogCount;
    u32 numdlgmessage;
    u32 fontCount;
    u32 colorDepth;
    u32 target;
    u32 dialogOptionsBullet;
    u16 inventoryHotspotMarkerDotColor;
    u16 crosshairColor;
    u32 uniqueId;
    u32 guiCount;
    u32 cursorCount;
    u32 resolutionType;
    u32 resolutionWidth;
    u32 resolutionHeight;
    u32 lipsyncDefaultFrame;
    u32 hotspotMarkerImage;
    padding[16 * sizeof(u32)]; // reserved
    u32 extensionOffset;
    u32 globalMessages[500];
    u32 dictNonNull;
    u32 globalScriptNotNull;
    u32 charsNotNull;
    u32 compiledScriptNotNull;
};

struct FontInfo {
    u32 flags;
    s32 sizeMultiplier;
    s32 outline;
    s32 verticalOffset;
    s32 lineSpacing;
};

struct InventoryItem {
    char description[24];
    padding[4];
    u32 image;
    u32 cursorImage;
    u32 hotspotX;
    u32 hotspotY;
    padding[5 * sizeof(u32)]; // reserved
    u32 startsWith;
    padding[3];
};

struct Cursor {
    u32 image;
    s16 hotspotX;
    s16 hotspotY;
    s16 view;
    char name[10]; // + null terminator
    u8 flags;
    padding[3];
};

struct InteractionScript {
    u32 scriptFunctionNamesLength;
    NullString scriptFunctionNames[scriptFunctionNamesLength];
};

struct SavedGame {
    char gameSignature[30];
    u32 gameDataVersion;
    u32 agsEditorVersionLength;
    char agsEditorVersion[agsEditorVersionLength];
    u32 extendedEngineCaps;
    GameSetup gameSetup;
    char guidAsString[MAX_GUID_LENGTH];
    char saveGameFileExtension[MAX_SG_EXT_LENGTH];
    char saveGameFolderName[MAX_SG_FOLDER_LEN];
    FontInfo fontInfos[gameSetup.fontCount];
    u32 topmostSprite;
    u8 spriteFlags[topmostSprite];
    u8 inventoryItemSlots[68];
    InventoryItem inventoryItems[gameSetup.inventoryItemCount - 1];
    Cursor cursors[gameSetup.cursorCount];
    InteractionScript characterInteractionScripts[gameSetup.characterCount];
    InteractionScript itemInteractionScripts[gameSetup.inventoryItemCount - 1];
    u32 textParserWordCount;
};

struct AgsData {
    char magic[5];
    u8 formatVersion;
    u8 dataFileIndex;
    
    if (dataFileIndex == 0) {
        ClibHeader clibHeader;
    }
    
    SavedGame game;
};

AgsData agsData @ 0x00;