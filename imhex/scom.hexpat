import std.string;
import type.magic;

using CString = std::string::NullString;

struct Export {
    CString export;
    u32 address;
};

struct Section {
    CString name;
    s32 offset;
};

// taken from https://github.com/adventuregamestudio/ags/blob/master/Common/script/cc_internal.h#L118
enum FixupType : u8 {
    NoFixup = 0, // no-op
    GlobalData = 1, // code[fixup] += &globaldata[0]
    Function = 2, // code[fixup] += &code[0]
    String = 3, // code[fixup] += &strings[0]
    Import = 4, // code[fixup] = &imported_thing[code[fixup]]
    DataData = 5, // globaldata[fixup] += &globaldata[0]
    Stack = 6, // code[fixup] += &stack[0]
};

struct AgsScript {
    type::Magic<"SCOM"> startSignature;
    u32 scomVersion;
    u32 globalDataSize;
    u32 codeSize;
    u32 stringsSize;
    
    if (globalDataSize > 0) u8 globalData[globalDataSize];
    if (codeSize > 0) u32 codeData[codeSize];
    if (stringsSize > 0) {
        u32 stringsStart = $;
        CString strings[while($ < stringsStart + stringsSize)];
    }
    
    u32 fixupsSize;
    if (fixupsSize > 0) {
        FixupType fixupTypes[fixupsSize];
        u32 fixups[fixupsSize];
    }
    
    u32 importsSize;
    CString imports[importsSize];
    
    u32 exportsSize;
    Export exports[exportsSize];
    
    u32 sectionsSize;
    Section sections[sectionsSize];
    
    type::Magic<"\xFE\xCA\xEF\xBE"> endSignature;
};

AgsScript script @ 0x00;