// God of War Native PC release setup.
//
// One self-contained Win32 executable with two modes:
//
//   gow-setup.exe --pack <stage dir> <output exe>
//       Build the release setup: append the staged package to a copy of this
//       executable. This is the call used by tools/pipeline/modules/distribution.ps1.
//
//   gow-setup.exe [--dir <folder>] [/S]
//       Install the appended package for the current user (no administrator rights).
//
// Payload format (verified without installing by tools/test/verify_setup.py):
//
//   [ PE image of this executable ] [ block 0 ] ... [ block N-1 ] [ footer ]
//
//   block  : uint32 rawSize | uint32 packedSize | packedSize bytes of cabinet.dll
//            compressed data. Every block is one independent compressed buffer.
//   footer : char[8] "GOWSETUP" | uint64 payloadStart | uint64 rawSize |
//            uint32 blocks | uint32 version (= 1)        (32 bytes, little endian)
//
// The uncompressed payload ("raw stream") is:
//
//   uint32 fileCount
//   fileCount * { uint16 nameLength | nameLength UTF-16 code units | uint64 fileSize }
//   the file contents, concatenated in the same order as the manifest
//
// No third-party library is used: compression is the Windows system cabinet.dll
// (loaded dynamically at run time) and the shell integration uses the shell's own
// COM APIs. The installer also writes the uninstaller (a copy of this image without
// the payload), uninstall.lst and the per-user Apps entry, so the installed game can
// be removed again.

#ifndef _WIN32
#error "gow-setup is a Windows-only program."
#endif

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX

#include <windows.h>
#include <objbase.h>
#include <shlobj.h>
#include <shobjidl.h>
#include <shellapi.h>

#include <algorithm>
#include <cstdarg>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

namespace {

// ---------------------------------------------------------------------------------------------------
// payload format
// ---------------------------------------------------------------------------------------------------

// Compression format of the system cabinet.dll. The same constant is used by
// tools/test/verify_setup.py, so the payload stays verifiable by that tool.
constexpr DWORD kCompressFormat = 5;

constexpr char kFooterMagic[8] = { 'G', 'O', 'W', 'S', 'E', 'T', 'U', 'P' };
constexpr uint32_t kFooterVersion = 1;

// Raw bytes per compressed block. Small enough to keep the memory bounded, large
// enough to keep the compression ratio good.
constexpr size_t kChunkSize = 8u * 1024u * 1024u;

#pragma pack(push, 1)
struct Footer {
    char magic[8];
    uint64_t payloadStart;  // offset of the first block inside the file
    uint64_t rawSize;       // size of the uncompressed payload stream
    uint32_t blocks;        // number of compressed blocks
    uint32_t version;
};
#pragma pack(pop)
static_assert(sizeof(Footer) == 32, "the footer layout must match tools/test/verify_setup.py");

// ---------------------------------------------------------------------------------------------------
// small helpers
// ---------------------------------------------------------------------------------------------------

void logLine(const char* format, ...) {
    va_list args;
    va_start(args, format);
    vprintf(format, args);
    va_end(args);
    fputc('\n', stdout);
    fflush(stdout);
}

// Converts a wide string to UTF-8 so it can be printed with %s: the log uses
// the narrow printf format, and a wide pointer printed with %s would stop at
// the first character.
std::string utf8(const wchar_t* text) {
    if (text == nullptr) {
        return std::string();
    }
    const int size = WideCharToMultiByte(CP_UTF8, 0, text, -1, nullptr, 0, nullptr, nullptr);
    if (size <= 1) {
        return std::string();
    }
    std::string result(static_cast<size_t>(size - 1), '\0');
    WideCharToMultiByte(CP_UTF8, 0, text, -1, result.data(), size, nullptr, nullptr);
    return result;
}

std::string utf8(const std::wstring& text) {
    return utf8(text.c_str());
}

std::wstring exePath() {
    std::vector<wchar_t> buffer(MAX_PATH);
    for (;;) {
        const DWORD length = GetModuleFileNameW(nullptr, buffer.data(), static_cast<DWORD>(buffer.size()));
        if (length == 0) {
            return std::wstring();
        }
        if (length < buffer.size() - 1) {
            return std::wstring(buffer.data(), length);
        }
        buffer.resize(buffer.size() * 2);
    }
}

std::wstring joinPath(const std::wstring& base, const std::wstring& leaf) {
    if (base.empty()) {
        return leaf;
    }
    std::wstring result = base;
    if (result.back() != L'\\' && result.back() != L'/') {
        result.push_back(L'\\');
    }
    result.append(leaf);
    return result;
}

// Replaces the extension of a path (the part after the last dot of the file
// name) with the given one.
std::wstring replaceExtension(const std::wstring& path, const std::wstring& extension) {
    const size_t slash = path.find_last_of(L"\\/");
    const size_t dot = path.find_last_of(L'.');
    if (dot == std::wstring::npos || (slash != std::wstring::npos && dot < slash)) {
        return path + extension;
    }
    return path.substr(0, dot) + extension;
}

bool isDirectory(const std::wstring& path) {
    const DWORD attributes = GetFileAttributesW(path.c_str());
    return attributes != INVALID_FILE_ATTRIBUTES && (attributes & FILE_ATTRIBUTE_DIRECTORY) != 0;
}

bool fileExists(const std::wstring& path) {
    return GetFileAttributesW(path.c_str()) != INVALID_FILE_ATTRIBUTES;
}

// True when child is base itself or lives below it. Both paths are compared
// case-insensitively, the way Windows compares file names.
bool isUnder(const std::wstring& child, const std::wstring& base) {
    if (base.empty()) {
        return false;
    }
    std::wstring prefix = base;
    if (prefix.back() != L'\\' && prefix.back() != L'/') {
        prefix.push_back(L'\\');
    }
    if (child.size() < prefix.size()) {
        return false;
    }
    return CompareStringOrdinal(child.c_str(), static_cast<int>(prefix.size()), prefix.c_str(),
                                static_cast<int>(prefix.size()), TRUE) == CSTR_EQUAL;
}

// Creates every missing directory of the path.
bool ensureDirectory(const std::wstring& path) {
    if (path.empty()) {
        return false;
    }
    if (isDirectory(path)) {
        return true;
    }
    std::wstring current;
    size_t index = 0;
    if (path.size() >= 2 && path[1] == L':') {
        current = path.substr(0, 2);
        index = 2;
        if (index < path.size() && (path[index] == L'\\' || path[index] == L'/')) {
            current.push_back(L'\\');
            ++index;
        }
    }
    while (index <= path.size()) {
        const size_t next = path.find_first_of(L"\\/", index);
        const std::wstring component = path.substr(index, next == std::wstring::npos ? std::wstring::npos : next - index);
        if (!component.empty()) {
            if (!current.empty() && current.back() != L'\\') {
                current.push_back(L'\\');
            }
            current.append(component);
            if (!isDirectory(current) && !CreateDirectoryW(current.c_str(), nullptr) &&
                GetLastError() != ERROR_ALREADY_EXISTS) {
                return false;
            }
        }
        if (next == std::wstring::npos) {
            break;
        }
        index = next + 1;
    }
    return isDirectory(path);
}

bool removeTree(const std::wstring& path) {
    const DWORD attributes = GetFileAttributesW(path.c_str());
    if (attributes == INVALID_FILE_ATTRIBUTES) {
        return true;
    }
    if ((attributes & FILE_ATTRIBUTE_DIRECTORY) == 0) {
        SetFileAttributesW(path.c_str(), FILE_ATTRIBUTE_NORMAL);
        return DeleteFileW(path.c_str()) != FALSE;
    }
    WIN32_FIND_DATAW findData{};
    const std::wstring pattern = joinPath(path, L"*");
    HANDLE find = FindFirstFileW(pattern.c_str(), &findData);
    if (find != INVALID_HANDLE_VALUE) {
        do {
            const std::wstring name = findData.cFileName;
            if (name == L"." || name == L"..") {
                continue;
            }
            removeTree(joinPath(path, name));
        } while (FindNextFileW(find, &findData));
        FindClose(find);
    }
    RemoveDirectoryW(path.c_str());
    return true;
}

// Removes the directories of a path that became empty, bottom up. The root itself is kept.
bool removeEmptyDirectories(const std::wstring& root, const std::wstring& relative) {
    if (relative.empty()) {
        return true;
    }
    std::wstring current = root;
    size_t index = 0;
    std::vector<std::wstring> parts;
    while (index <= relative.size()) {
        const size_t next = relative.find_first_of(L"\\/", index);
        const std::wstring component =
            relative.substr(index, next == std::wstring::npos ? std::wstring::npos : next - index);
        if (!component.empty()) {
            parts.push_back(component);
        }
        if (next == std::wstring::npos) {
            break;
        }
        index = next + 1;
    }
    for (size_t i = parts.size(); i > 0; --i) {
        current = joinPath(current, parts[i - 1]);
        if (!isDirectory(current)) {
            return true;
        }
        WIN32_FIND_DATAW findData{};
        HANDLE find = FindFirstFileW(joinPath(current, L"*").c_str(), &findData);
        bool empty = (find == INVALID_HANDLE_VALUE);
        if (!empty) {
            FindClose(find);
        }
        if (!empty) {
            return true;
        }
        if (!RemoveDirectoryW(current.c_str())) {
            return true;
        }
    }
    return true;
}

bool readWholeFile(const std::wstring& path, std::vector<uint8_t>& out) {
    out.clear();
    HANDLE file = CreateFileW(path.c_str(), GENERIC_READ, FILE_SHARE_READ, nullptr, OPEN_EXISTING,
                              FILE_ATTRIBUTE_NORMAL, nullptr);
    if (file == INVALID_HANDLE_VALUE) {
        return false;
    }
    LARGE_INTEGER size{};
    if (!GetFileSizeEx(file, &size)) {
        CloseHandle(file);
        return false;
    }
    out.resize(static_cast<size_t>(size.QuadPart));
    size_t done = 0;
    while (done < out.size()) {
        DWORD read = 0;
        const DWORD chunk = static_cast<DWORD>(std::min<size_t>(out.size() - done, 1u << 20));
        if (!ReadFile(file, out.data() + done, chunk, &read, nullptr) || read == 0) {
            CloseHandle(file);
            out.clear();
            return false;
        }
        done += read;
    }
    CloseHandle(file);
    return true;
}

bool writeWholeFile(const std::wstring& path, const void* data, size_t size) {
    HANDLE file = CreateFileW(path.c_str(), GENERIC_WRITE, 0, nullptr, CREATE_ALWAYS,
                              FILE_ATTRIBUTE_NORMAL, nullptr);
    if (file == INVALID_HANDLE_VALUE) {
        return false;
    }
    const uint8_t* bytes = static_cast<const uint8_t*>(data);
    size_t done = 0;
    while (done < size) {
        DWORD written = 0;
        const DWORD chunk = static_cast<DWORD>(std::min<size_t>(size - done, 1u << 20));
        if (!WriteFile(file, bytes + done, chunk, &written, nullptr) || written == 0) {
            CloseHandle(file);
            return false;
        }
        done += written;
    }
    CloseHandle(file);
    return true;
}

std::string timestampSuffix() {
    SYSTEMTIME time{};
    GetLocalTime(&time);
    char buffer[32];
    _snprintf_s(buffer, sizeof(buffer), _TRUNCATE, "%04u%02u%02u-%02u%02u%02u", time.wYear,
                time.wMonth, time.wDay, time.wHour, time.wMinute, time.wSecond);
    return std::string(buffer);
}

// ---------------------------------------------------------------------------------------------------
// system compression (cabinet.dll), loaded dynamically so the executable imports no extra library
// ---------------------------------------------------------------------------------------------------

using CompressorHandle = void*;

struct CabinetApi {
    HMODULE module = nullptr;
    BOOL(WINAPI* createCompressor)(DWORD, LPCVOID, CompressorHandle*) = nullptr;
    BOOL(WINAPI* compress)(CompressorHandle, void*, size_t, void*, size_t, size_t*) = nullptr;
    BOOL(WINAPI* closeCompressor)(CompressorHandle) = nullptr;
    BOOL(WINAPI* createDecompressor)(DWORD, LPCVOID, CompressorHandle*) = nullptr;
    BOOL(WINAPI* decompress)(CompressorHandle, void*, size_t, void*, size_t, size_t*) = nullptr;
    BOOL(WINAPI* closeDecompressor)(CompressorHandle) = nullptr;
};

bool loadCabinet(CabinetApi& api) {
    api.module = LoadLibraryW(L"cabinet.dll");
    if (api.module == nullptr) {
        return false;
    }
    api.createCompressor =
        reinterpret_cast<BOOL(WINAPI*)(DWORD, LPCVOID, CompressorHandle*)>(GetProcAddress(api.module, "CreateCompressor"));
    api.compress = reinterpret_cast<BOOL(WINAPI*)(CompressorHandle, void*, size_t, void*, size_t, size_t*)>(
        GetProcAddress(api.module, "Compress"));
    api.closeCompressor = reinterpret_cast<BOOL(WINAPI*)(CompressorHandle)>(GetProcAddress(api.module, "CloseCompressor"));
    api.createDecompressor =
        reinterpret_cast<BOOL(WINAPI*)(DWORD, LPCVOID, CompressorHandle*)>(GetProcAddress(api.module, "CreateDecompressor"));
    api.decompress = reinterpret_cast<BOOL(WINAPI*)(CompressorHandle, void*, size_t, void*, size_t, size_t*)>(
        GetProcAddress(api.module, "Decompress"));
    api.closeDecompressor =
        reinterpret_cast<BOOL(WINAPI*)(CompressorHandle)>(GetProcAddress(api.module, "CloseDecompressor"));
    return api.createCompressor && api.compress && api.closeCompressor && api.createDecompressor &&
           api.decompress && api.closeDecompressor;
}

// Compresses one chunk into one self-contained compressed buffer.
bool compressChunk(const CabinetApi& api, const uint8_t* data, size_t size, std::vector<uint8_t>& out) {
    CompressorHandle handle = nullptr;
    if (!api.createCompressor(kCompressFormat, nullptr, &handle)) {
        return false;
    }
    size_t capacity = size + size / 8 + 4096;
    bool ok = false;
    for (int attempt = 0; attempt < 4 && !ok; ++attempt) {
        out.assign(capacity, 0);
        size_t produced = 0;
        if (api.compress(handle, const_cast<uint8_t*>(data), size, out.data(), out.size(), &produced)) {
            out.resize(produced);
            ok = true;
            break;
        }
        if (GetLastError() != ERROR_INSUFFICIENT_BUFFER) {
            break;
        }
        capacity *= 2;
    }
    api.closeCompressor(handle);
    return ok;
}

// Decompresses one block; the result must fill the whole output buffer.
bool decompressChunk(const CabinetApi& api, const uint8_t* data, size_t size, uint8_t* out, size_t outSize) {
    CompressorHandle handle = nullptr;
    if (!api.createDecompressor(kCompressFormat, nullptr, &handle)) {
        return false;
    }
    size_t produced = 0;
    const BOOL ok = api.decompress(handle, out, outSize, const_cast<uint8_t*>(data), size, &produced);
    api.closeDecompressor(handle);
    return ok && produced == outSize;
}

// ---------------------------------------------------------------------------------------------------
// stage directory
// ---------------------------------------------------------------------------------------------------

struct StageFile {
    std::wstring relative;  // relative path, backslash separated
    uint64_t size = 0;
};

// Collects every regular file of the directory tree, sorted by path so the payload is reproducible.
bool collectStage(const std::wstring& root, std::vector<StageFile>& files) {
    std::vector<std::wstring> pending;
    pending.push_back(root);
    while (!pending.empty()) {
        const std::wstring directory = pending.back();
        pending.pop_back();
        WIN32_FIND_DATAW findData{};
        HANDLE find = FindFirstFileW(joinPath(directory, L"*").c_str(), &findData);
        if (find == INVALID_HANDLE_VALUE) {
            continue;
        }
        do {
            const std::wstring name = findData.cFileName;
            if (name == L"." || name == L"..") {
                continue;
            }
            if ((findData.dwFileAttributes & FILE_ATTRIBUTE_REPARSE_POINT) != 0) {
                continue;  // links and junctions are not part of the release
            }
            const std::wstring full = joinPath(directory, name);
            std::wstring relative = name;
            if (directory.size() > root.size()) {
                relative = directory.substr(root.size() + 1) + L"\\" + name;
            }
            if ((findData.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) != 0) {
                pending.push_back(full);
            } else {
                StageFile entry;
                entry.relative = relative;
                entry.size = (static_cast<uint64_t>(findData.nFileSizeHigh) << 32) | findData.nFileSizeLow;
                files.push_back(entry);
            }
        } while (FindNextFileW(find, &findData));
        FindClose(find);
    }
    std::sort(files.begin(), files.end(), [](const StageFile& a, const StageFile& b) {
        const int order = CompareStringOrdinal(a.relative.c_str(), -1, b.relative.c_str(), -1, TRUE);
        if (order != CSTR_EQUAL) {
            return order == CSTR_LESS_THAN;
        }
        return a.relative < b.relative;
    });
    return true;
}

// ---------------------------------------------------------------------------------------------------
// path safety
// ---------------------------------------------------------------------------------------------------

// Accepts a relative path made of plain names. Absolute paths, drive letters, "..", "." and
// characters Windows forbids are rejected, so an entry can never leave the install folder.
bool isSafeRelativePath(const std::wstring& name) {
    if (name.empty() || name.size() > 32768) {
        return false;
    }
    if (name.find(L':') != std::wstring::npos) {
        return false;  // drive letter or alternate data stream
    }
    if (name[0] == L'\\' || name[0] == L'/') {
        return false;  // absolute
    }
    if (name.find(L"//") != std::wstring::npos) {
        return false;
    }
    size_t index = 0;
    while (index <= name.size()) {
        const size_t next = name.find_first_of(L"\\/", index);
        const std::wstring component =
            name.substr(index, next == std::wstring::npos ? std::wstring::npos : next - index);
        if (component.empty() || component == L"." || component == L"..") {
            return false;
        }
        if (component.find_first_of(L"*?\"<>|") != std::wstring::npos) {
            return false;
        }
        if (!component.empty() && (component.back() == L' ' || component.back() == L'.')) {
            return false;  // Windows would strip these and change the name
        }
        if (next == std::wstring::npos) {
            break;
        }
        index = next + 1;
    }
    return true;
}

// ---------------------------------------------------------------------------------------------------
// pack
// ---------------------------------------------------------------------------------------------------

bool appendBytes(HANDLE file, const void* data, size_t size) {
    const uint8_t* bytes = static_cast<const uint8_t*>(data);
    size_t done = 0;
    while (done < size) {
        DWORD written = 0;
        const DWORD chunk = static_cast<DWORD>(std::min<size_t>(size - done, 1u << 20));
        if (!WriteFile(file, bytes + done, chunk, &written, nullptr) || written == 0) {
            return false;
        }
        done += written;
    }
    return true;
}

int packStage(const std::wstring& stage, const std::wstring& output) {
    if (!isDirectory(stage)) {
        logLine("ERROR: the stage directory does not exist: %s", utf8(stage).c_str());
        return 1;
    }
    std::vector<StageFile> files;
    collectStage(stage, files);
    if (files.empty()) {
        logLine("ERROR: the stage directory has no files: %s", utf8(stage).c_str());
        return 1;
    }
    uint64_t total = 0;
    for (const StageFile& file : files) {
        total += file.size;
    }
    logLine("packing %zu files (%.1f MB) into %s", files.size(), static_cast<double>(total) / (1024.0 * 1024.0),
            utf8(output).c_str());

    // The raw stream: the manifest first, then the file contents in the same order.
    const std::wstring rawPath = output + L".raw.tmp";
    HANDLE raw = CreateFileW(rawPath.c_str(), GENERIC_READ | GENERIC_WRITE, 0, nullptr, CREATE_ALWAYS,
                             FILE_ATTRIBUTE_NORMAL, nullptr);
    if (raw == INVALID_HANDLE_VALUE) {
        logLine("ERROR: cannot create the temporary payload file: %s", utf8(rawPath).c_str());
        return 1;
    }
    const uint32_t count = static_cast<uint32_t>(files.size());
    bool ok = appendBytes(raw, &count, sizeof(count));
    for (size_t i = 0; ok && i < files.size(); ++i) {
        const std::wstring& name = files[i].relative;
        if (name.size() > 0xFFFF) {
            logLine("ERROR: the path is too long for the manifest: %s", utf8(name).c_str());
            ok = false;
            break;
        }
        const uint16_t length = static_cast<uint16_t>(name.size());
        ok = appendBytes(raw, &length, sizeof(length));
        const std::vector<uint8_t> utf16(reinterpret_cast<const uint8_t*>(name.c_str()),
                                         reinterpret_cast<const uint8_t*>(name.c_str()) + name.size() * sizeof(wchar_t));
        ok = ok && appendBytes(raw, utf16.data(), utf16.size());
        ok = ok && appendBytes(raw, &files[i].size, sizeof(files[i].size));
    }
    for (size_t i = 0; ok && i < files.size(); ++i) {
        const std::wstring full = joinPath(stage, files[i].relative);
        HANDLE source = CreateFileW(full.c_str(), GENERIC_READ, FILE_SHARE_READ, nullptr, OPEN_EXISTING,
                                    FILE_ATTRIBUTE_NORMAL, nullptr);
        if (source == INVALID_HANDLE_VALUE) {
            logLine("ERROR: cannot read %s", utf8(full).c_str());
            ok = false;
            break;
        }
        std::vector<uint8_t> buffer(1u << 20);
        for (;;) {
            DWORD read = 0;
            if (!ReadFile(source, buffer.data(), static_cast<DWORD>(buffer.size()), &read, nullptr)) {
                ok = false;
                break;
            }
            if (read == 0) {
                break;
            }
            if (!appendBytes(raw, buffer.data(), read)) {
                ok = false;
                break;
            }
        }
        CloseHandle(source);
    }
    LARGE_INTEGER rawSize{};
    if (ok) {
        GetFileSizeEx(raw, &rawSize);
    }
    CloseHandle(raw);
    if (!ok) {
        DeleteFileW(rawPath.c_str());
        return 1;
    }

    // The output: a copy of this executable, the compressed blocks and the footer.
    std::vector<uint8_t> image;
    if (!readWholeFile(exePath(), image)) {
        DeleteFileW(rawPath.c_str());
        logLine("ERROR: cannot read this executable.");
        return 1;
    }
    HANDLE target = CreateFileW(output.c_str(), GENERIC_WRITE, 0, nullptr, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL,
                                nullptr);
    if (target == INVALID_HANDLE_VALUE) {
        DeleteFileW(rawPath.c_str());
        logLine("ERROR: cannot create %s", utf8(output).c_str());
        return 1;
    }
    ok = appendBytes(target, image.data(), image.size());
    const uint64_t payloadStart = image.size();

    CabinetApi api;
    if (ok && !loadCabinet(api)) {
        logLine("ERROR: the system compression library (cabinet.dll) is not available.");
        ok = false;
    }
    HANDLE input = ok ? CreateFileW(rawPath.c_str(), GENERIC_READ, FILE_SHARE_READ, nullptr, OPEN_EXISTING,
                                     FILE_ATTRIBUTE_NORMAL, nullptr)
                       : INVALID_HANDLE_VALUE;
    if (ok && input == INVALID_HANDLE_VALUE) {
        logLine("ERROR: cannot reopen the temporary payload file.");
        ok = false;
    }
    uint32_t blocks = 0;
    std::vector<uint8_t> chunk(kChunkSize);
    std::vector<uint8_t> packed;
    while (ok) {
        DWORD read = 0;
        if (!ReadFile(input, chunk.data(), static_cast<DWORD>(chunk.size()), &read, nullptr)) {
            ok = false;
            break;
        }
        if (read == 0) {
            break;
        }
        if (!compressChunk(api, chunk.data(), read, packed)) {
            logLine("ERROR: compression failed.");
            ok = false;
            break;
        }
        const uint32_t rawLength = read;
        const uint32_t packedLength = static_cast<uint32_t>(packed.size());
        ok = appendBytes(target, &rawLength, sizeof(rawLength)) && appendBytes(target, &packedLength, sizeof(packedLength)) &&
             appendBytes(target, packed.data(), packed.size());
        if (ok) {
            ++blocks;
        }
    }
    if (input != INVALID_HANDLE_VALUE) {
        CloseHandle(input);
    }
    if (ok) {
        Footer footer{};
        memcpy(footer.magic, kFooterMagic, sizeof(kFooterMagic));
        footer.payloadStart = payloadStart;
        footer.rawSize = static_cast<uint64_t>(rawSize.QuadPart);
        footer.blocks = blocks;
        footer.version = kFooterVersion;
        ok = appendBytes(target, &footer, sizeof(footer));
    }
    CloseHandle(target);
    DeleteFileW(rawPath.c_str());
    if (!ok) {
        DeleteFileW(output.c_str());
        return 1;
    }
    logLine("OK: %s (%u blocks, %llu unpacked bytes)", utf8(output).c_str(), blocks,
            static_cast<unsigned long long>(rawSize.QuadPart));
    return 0;
}

// ---------------------------------------------------------------------------------------------------
// payload reader
// ---------------------------------------------------------------------------------------------------

struct ManifestEntry {
    std::wstring name;
    uint64_t size = 0;
    uint64_t offset = 0;  // offset of the content inside the raw stream
};

// Reads the footer of an executable and reports where the payload starts.
bool readFooter(const std::wstring& path, Footer& footer, uint64_t& fileSize) {
    HANDLE file = CreateFileW(path.c_str(), GENERIC_READ, FILE_SHARE_READ, nullptr, OPEN_EXISTING,
                              FILE_ATTRIBUTE_NORMAL, nullptr);
    if (file == INVALID_HANDLE_VALUE) {
        return false;
    }
    LARGE_INTEGER size{};
    bool ok = GetFileSizeEx(file, &size) != FALSE;
    uint64_t total = 0;
    if (ok) {
        total = static_cast<uint64_t>(size.QuadPart);
        if (total < sizeof(Footer)) {
            ok = false;
        }
    }
    if (ok) {
        LARGE_INTEGER position{};
        position.QuadPart = static_cast<LONGLONG>(total - sizeof(Footer));
        ok = SetFilePointerEx(file, position, nullptr, FILE_BEGIN) != FALSE &&
             ReadFile(file, &footer, sizeof(footer), nullptr, nullptr) != FALSE;
    }
    CloseHandle(file);
    if (!ok) {
        return false;
    }
    if (memcmp(footer.magic, kFooterMagic, sizeof(kFooterMagic)) != 0 || footer.version != kFooterVersion) {
        return false;
    }
    if (footer.payloadStart == 0 || footer.payloadStart >= total - sizeof(Footer) || footer.blocks == 0) {
        return false;
    }
    fileSize = total;
    return true;
}

// Unpacks the payload of an executable into a raw stream file and returns its manifest.
bool unpackPayload(const std::wstring& path, const std::wstring& rawPath, std::vector<ManifestEntry>& entries,
                    uint64_t& rawSize) {
    Footer footer{};
    uint64_t fileSize = 0;
    if (!readFooter(path, footer, fileSize)) {
        logLine("ERROR: the installer is damaged: download it again.");
        return false;
    }
    HANDLE input = CreateFileW(path.c_str(), GENERIC_READ, FILE_SHARE_READ, nullptr, OPEN_EXISTING,
                              FILE_ATTRIBUTE_NORMAL, nullptr);
    if (input == INVALID_HANDLE_VALUE) {
        logLine("ERROR: cannot read the installer.");
        return false;
    }
    HANDLE raw = CreateFileW(rawPath.c_str(), GENERIC_READ | GENERIC_WRITE, 0, nullptr, CREATE_ALWAYS,
                             FILE_ATTRIBUTE_NORMAL, nullptr);
    if (raw == INVALID_HANDLE_VALUE) {
        CloseHandle(input);
        logLine("ERROR: cannot create the temporary payload file.");
        return false;
    }
    CabinetApi api;
    if (!loadCabinet(api)) {
        CloseHandle(input);
        CloseHandle(raw);
        logLine("ERROR: the system compression library (cabinet.dll) is not available.");
        return false;
    }
    uint64_t position = footer.payloadStart;
    uint64_t written = 0;
    bool ok = true;
    std::vector<uint8_t> block;
    std::vector<uint8_t> plain;
    for (uint32_t index = 0; ok && index < footer.blocks; ++index) {
        LARGE_INTEGER at{};
        at.QuadPart = static_cast<LONGLONG>(position);
        uint32_t header[2] = { 0, 0 };
        ok = SetFilePointerEx(input, at, nullptr, FILE_BEGIN) != FALSE &&
             ReadFile(input, header, sizeof(header), nullptr, nullptr) != FALSE;
        if (!ok) {
            break;
        }
        position += sizeof(header);
        const uint32_t rawLength = header[0];
        const uint32_t packedLength = header[1];
        if (rawLength == 0 || rawLength > 64u * 1024u * 1024u || position + packedLength > fileSize - sizeof(Footer)) {
            ok = false;
            break;
        }
        block.resize(packedLength);
        ok = ReadFile(input, block.data(), packedLength, nullptr, nullptr) != FALSE;
        position += packedLength;
        if (!ok) {
            break;
        }
        plain.resize(rawLength);
        if (!decompressChunk(api, block.data(), block.size(), plain.data(), plain.size())) {
            logLine("ERROR: the installer is damaged: download it again.");
            ok = false;
            break;
        }
        if (!appendBytes(raw, plain.data(), plain.size())) {
            ok = false;
            break;
        }
        written += rawLength;
    }
    CloseHandle(input);
    CloseHandle(raw);
    if (!ok) {
        return false;
    }
    if (written != footer.rawSize) {
        logLine("ERROR: the installer is damaged: download it again.");
        return false;
    }
    rawSize = written;

    // The manifest.
    HANDLE manifest = CreateFileW(rawPath.c_str(), GENERIC_READ, FILE_SHARE_READ, nullptr, OPEN_EXISTING,
                                  FILE_ATTRIBUTE_NORMAL, nullptr);
    if (manifest == INVALID_HANDLE_VALUE) {
        return false;
    }
    uint32_t count = 0;
    ok = ReadFile(manifest, &count, sizeof(count), nullptr, nullptr) != FALSE;
    uint64_t offset = sizeof(count);
    for (uint32_t index = 0; ok && index < count; ++index) {
        uint16_t length = 0;
        ok = ReadFile(manifest, &length, sizeof(length), nullptr, nullptr) != FALSE;
        if (!ok) {
            break;
        }
        offset += sizeof(length);
        std::wstring name(length, L'\0');
        if (length > 0) {
            ok = ReadFile(manifest, name.data(), static_cast<DWORD>(length * sizeof(wchar_t)), nullptr, nullptr) != FALSE;
        }
        if (!ok) {
            break;
        }
        offset += static_cast<uint64_t>(length) * sizeof(wchar_t);
        ManifestEntry entry;
        entry.name = name;
        ok = ReadFile(manifest, &entry.size, sizeof(entry.size), nullptr, nullptr) != FALSE;
        if (!ok) {
            break;
        }
        offset += sizeof(entry.size);
        entry.offset = offset;
        entries.push_back(entry);
        offset += entry.size;
    }
    CloseHandle(manifest);
    if (!ok) {
        logLine("ERROR: the installer is damaged: download it again.");
        return false;
    }
    if (offset != rawSize) {
        logLine("ERROR: the installer is damaged: download it again.");
        return false;
    }
    return true;
}

// ---------------------------------------------------------------------------------------------------
// shell integration
// ---------------------------------------------------------------------------------------------------

bool knownFolder(const GUID& id, std::wstring& path) {
    PWSTR raw = nullptr;
    if (FAILED(SHGetKnownFolderPath(id, 0, nullptr, &raw)) || raw == nullptr) {
        return false;
    }
    path.assign(raw);
    CoTaskMemFree(raw);
    return true;
}

bool createShortcut(const std::wstring& link, const std::wstring& target, const std::wstring& workingDirectory,
                     const std::wstring& description) {
    IShellLinkW* shellLink = nullptr;
    if (FAILED(CoCreateInstance(CLSID_ShellLink, nullptr, CLSCTX_INPROC_SERVER, IID_IShellLinkW,
                                reinterpret_cast<void**>(&shellLink)))) {
        return false;
    }
    shellLink->SetPath(target.c_str());
    shellLink->SetWorkingDirectory(workingDirectory.c_str());
    shellLink->SetDescription(description.c_str());
    shellLink->SetIconLocation(target.c_str(), 0);
    IPersistFile* persist = nullptr;
    bool ok = SUCCEEDED(shellLink->QueryInterface(IID_IPersistFile, reinterpret_cast<void**>(&persist))) &&
              SUCCEEDED(persist->Save(link.c_str(), TRUE));
    if (persist) {
        persist->Release();
    }
    shellLink->Release();
    return ok;
}

void registerUninstall(const std::wstring& installDirectory, const std::wstring& launcher, uint64_t installedBytes) {
    HKEY key = nullptr;
    if (RegCreateKeyExW(HKEY_CURRENT_USER,
                        L"Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\gow-native-pc", 0, nullptr,
                        REG_OPTION_NON_VOLATILE, KEY_WRITE, nullptr, &key, nullptr) != ERROR_SUCCESS) {
        return;
    }
    const auto setString = [key](const wchar_t* name, const std::wstring& value) {
        RegSetValueExW(key, name, 0, REG_SZ, reinterpret_cast<const BYTE*>(value.c_str()),
                       static_cast<DWORD>((value.size() + 1) * sizeof(wchar_t)));
    };
    setString(L"DisplayName", L"God of War Native PC");
    setString(L"DisplayVersion", L"0.5.0");
    setString(L"Publisher", L"gow-native-pc");
    setString(L"DisplayIcon", launcher);
    setString(L"InstallLocation", installDirectory);
    setString(L"URLInfoAbout", L"https://github.com/Vnnc1/gow-native-pc");
    setString(L"UninstallString", L"\"" + joinPath(installDirectory, L"uninstall.exe") + L"\" /uninstall");
    RegSetValueExW(key, L"NoModify", 0, REG_DWORD, reinterpret_cast<const BYTE*>(L"\1\0\0\0"), 4);
    RegSetValueExW(key, L"NoRepair", 0, REG_DWORD, reinterpret_cast<const BYTE*>(L"\1\0\0\0"), 4);
    const DWORD estimated = static_cast<DWORD>(installedBytes / 1024);
    RegSetValueExW(key, L"EstimatedSize", 0, REG_DWORD, reinterpret_cast<const BYTE*>(&estimated), sizeof(estimated));
    RegCloseKey(key);
}

void unregisterUninstall() {
    RegDeleteKeyW(HKEY_CURRENT_USER, L"Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\gow-native-pc");
}

// Writes the list of installed files, UTF-16LE with a byte order mark, like the other tools of the project.
bool writeUninstallList(const std::wstring& path, const std::vector<ManifestEntry>& entries) {
    std::vector<uint8_t> bytes;
    bytes.push_back(0xFF);
    bytes.push_back(0xFE);
    const auto append = [&bytes](const std::wstring& text) {
        const uint8_t* raw = reinterpret_cast<const uint8_t*>(text.c_str());
        bytes.insert(bytes.end(), raw, raw + text.size() * sizeof(wchar_t));
    };
    for (const ManifestEntry& entry : entries) {
        append(entry.name);
        append(L"\r\n");
    }
    return writeWholeFile(path, bytes.data(), bytes.size());
}

bool readUninstallList(const std::wstring& path, std::vector<std::wstring>& names) {
    std::vector<uint8_t> bytes;
    if (!readWholeFile(path, bytes)) {
        return false;
    }
    size_t offset = 0;
    if (bytes.size() >= 2 && bytes[0] == 0xFF && bytes[1] == 0xFE) {
        offset = 2;
    }
    std::wstring text;
    for (size_t i = offset; i + 1 < bytes.size(); i += 2) {
        text.push_back(static_cast<wchar_t>(bytes[i] | (bytes[i + 1] << 8)));
    }
    size_t index = 0;
    while (index <= text.size()) {
        const size_t next = text.find(L'\n', index);
        std::wstring line = text.substr(index, next == std::wstring::npos ? std::wstring::npos : next - index);
        while (!line.empty() && (line.back() == L'\r' || line.back() == L'\n')) {
            line.pop_back();
        }
        if (!line.empty()) {
            names.push_back(line);
        }
        if (next == std::wstring::npos) {
            break;
        }
        index = next + 1;
    }
    return true;
}

// ---------------------------------------------------------------------------------------------------
// install
// ---------------------------------------------------------------------------------------------------

struct Options {
    bool silent = false;
    bool uninstall = false;
    bool purge = false;
    std::wstring directory;
    std::wstring uninstallFrom;
};

std::wstring defaultInstallDirectory() {
    std::wstring localAppData;
    if (!knownFolder(FOLDERID_LocalAppData, localAppData) || localAppData.empty()) {
        localAppData = joinPath(exePath(), L"..");
    }
    return joinPath(localAppData, L"Programs\\gow-native-pc");
}

void showResult(const wchar_t* title, const std::wstring& text, bool silent) {
    if (!silent) {
        MessageBoxW(nullptr, text.c_str(), title, MB_OK | MB_ICONINFORMATION);
    }
}

int installPayload(const std::wstring& selfPath, const Options& options) {
    std::wstring target = options.directory.empty() ? defaultInstallDirectory() : options.directory;
    while (target.size() > 1 && (target.back() == L'\\' || target.back() == L'/')) {
        target.pop_back();
    }
    logLine("install folder: %s", utf8(target).c_str());

    wchar_t tempPath[MAX_PATH]{};
    if (GetTempPathW(MAX_PATH, tempPath) == 0) {
        logLine("ERROR: the temporary folder is not available.");
        return 1;
    }
    wchar_t rawName[MAX_PATH]{};
    // GetTempFileNameW takes the unique number as its third argument, not the
    // extension: the .raw suffix is applied afterwards.
    if (GetTempFileNameW(tempPath, L"gow", 0, rawName) == 0) {
        logLine("ERROR: cannot create a temporary file.");
        return 1;
    }
    const std::wstring rawPath = replaceExtension(rawName, L".raw");
    std::vector<ManifestEntry> entries;
    uint64_t rawSize = 0;
    const bool unpacked = unpackPayload(selfPath, rawPath, entries, rawSize);
    if (!unpacked) {
        DeleteFileW(rawPath.c_str());
        return 1;
    }
    logLine("payload: %zu files, %llu bytes", entries.size(), static_cast<unsigned long long>(rawSize));

    // Every entry is checked before a single byte is written: a path that would leave the
    // install folder aborts the whole installation.
    for (const ManifestEntry& entry : entries) {
        if (!isSafeRelativePath(entry.name)) {
            logLine("ERROR: the installer is damaged: unsafe path in the payload.");
            DeleteFileW(rawPath.c_str());
            return 1;
        }
        const std::wstring destination = joinPath(target, entry.name);
        if (!isUnder(destination, target)) {
            logLine("ERROR: the installer is damaged: unsafe path in the payload.");
            DeleteFileW(rawPath.c_str());
            return 1;
        }
    }

    // An existing folder is kept as a backup next to it, so nothing is lost.
    if (isDirectory(target)) {
        WIN32_FIND_DATAW findData{};
        HANDLE find = FindFirstFileW(joinPath(target, L"*").c_str(), &findData);
        bool empty = (find == INVALID_HANDLE_VALUE);
        if (!empty) {
            FindClose(find);
        }
        if (!empty) {
            const std::wstring backup = target + L".old-" + std::wstring(timestampSuffix().begin(), timestampSuffix().end());
            logLine("the install folder already has files: it is kept as %s", utf8(backup).c_str());
            if (!MoveFileW(target.c_str(), backup.c_str())) {
                logLine("ERROR: cannot move the previous installation aside: %lu", GetLastError());
                DeleteFileW(rawPath.c_str());
                return 1;
            }
        }
    }
    if (!ensureDirectory(target)) {
        logLine("ERROR: cannot create the install folder: %s", utf8(target).c_str());
        DeleteFileW(rawPath.c_str());
        return 1;
    }

    HANDLE raw = CreateFileW(rawPath.c_str(), GENERIC_READ, FILE_SHARE_READ, nullptr, OPEN_EXISTING,
                             FILE_ATTRIBUTE_NORMAL, nullptr);
    if (raw == INVALID_HANDLE_VALUE) {
        logLine("ERROR: cannot read the temporary payload file.");
        DeleteFileW(rawPath.c_str());
        return 1;
    }
    uint64_t installed = 0;
    std::vector<uint8_t> buffer(1u << 20);
    bool ok = true;
    for (size_t index = 0; ok && index < entries.size(); ++index) {
        const ManifestEntry& entry = entries[index];
        const std::wstring destination = joinPath(target, entry.name);
        const std::wstring parent = destination.substr(0, destination.find_last_of(L"\\"));
        if (!parent.empty() && !ensureDirectory(parent)) {
            logLine("ERROR: cannot create %s", utf8(parent).c_str());
            ok = false;
            break;
        }
        HANDLE targetFile = CreateFileW(destination.c_str(), GENERIC_WRITE, 0, nullptr, CREATE_ALWAYS,
                                        FILE_ATTRIBUTE_NORMAL, nullptr);
        if (targetFile == INVALID_HANDLE_VALUE) {
            logLine("ERROR: cannot write %s", utf8(destination).c_str());
            ok = false;
            break;
        }
        LARGE_INTEGER at{};
        at.QuadPart = static_cast<LONGLONG>(entry.offset);
        SetFilePointerEx(raw, at, nullptr, FILE_BEGIN);
        uint64_t left = entry.size;
        while (left > 0) {
            DWORD read = 0;
            const DWORD chunk = static_cast<DWORD>(std::min<uint64_t>(left, buffer.size()));
            if (!ReadFile(raw, buffer.data(), chunk, &read, nullptr) || read == 0) {
                ok = false;
                break;
            }
            DWORD written = 0;
            if (!WriteFile(targetFile, buffer.data(), read, &written, nullptr) || written != read) {
                ok = false;
                break;
            }
            left -= read;
            installed += read;
        }
        CloseHandle(targetFile);
        if (!ok) {
            break;
        }
        if ((index + 1) % 128 == 0 || index + 1 == entries.size()) {
            logLine("  %zu/%zu files", index + 1, entries.size());
        }
    }
    CloseHandle(raw);
    DeleteFileW(rawPath.c_str());
    if (!ok) {
        logLine("ERROR: the installation failed.");
        return 1;
    }

    // The launcher the shortcuts point at.
    const std::wstring launcher = joinPath(target, L"launcher\\bin\\gow-launcher.exe");
    const bool hasLauncher = fileExists(launcher);
    if (hasLauncher) {
        std::wstring programs;
        if (knownFolder(FOLDERID_Programs, programs)) {
            const std::wstring link = joinPath(programs, L"God of War Native PC.lnk");
            if (createShortcut(link, launcher, joinPath(target, L"launcher\\bin"), L"God of War Native PC")) {
                logLine("start menu shortcut: %s", utf8(link).c_str());
            } else {
                logLine("WARNING: the start menu shortcut could not be created.");
            }
        }
        std::wstring desktop;
        if (knownFolder(FOLDERID_Desktop, desktop)) {
            const std::wstring link = joinPath(desktop, L"God of War Launcher.lnk");
            if (createShortcut(link, launcher, joinPath(target, L"launcher\\bin"), L"God of War Native PC")) {
                logLine("desktop shortcut: %s", utf8(link).c_str());
            }
        }
    } else {
        logLine("WARNING: %s is missing, no shortcut was created.", utf8(launcher).c_str());
    }

    // The uninstaller: this image without the payload, so it stays small.
    Footer footer{};
    uint64_t fileSize = 0;
    std::vector<uint8_t> image;
    if (readFooter(selfPath, footer, fileSize) && readWholeFile(selfPath, image)) {
        image.resize(static_cast<size_t>(footer.payloadStart));
        if (!writeWholeFile(joinPath(target, L"uninstall.exe"), image.data(), image.size())) {
            logLine("WARNING: the uninstaller could not be written.");
        }
    }
    writeUninstallList(joinPath(target, L"uninstall.lst"), entries);
    registerUninstall(target, launcher, installed);
    logLine("OK: installed %llu bytes in %s", static_cast<unsigned long long>(installed), utf8(target).c_str());
    if (hasLauncher) {
        logLine("open the launcher: it downloads the runtime, takes your ISO and builds the game.");
    }
    showResult(L"God of War Native PC", L"Installed in:\n" + target, options.silent);
    return 0;
}

// ---------------------------------------------------------------------------------------------------
// uninstall
// ---------------------------------------------------------------------------------------------------

// Removes the build folder of an installed copy, but only when its CMake cache really points
// inside the install folder.
void purgeBuildFolder(const std::wstring& installDirectory) {
    const std::wstring pointer = joinPath(installDirectory, L"data\\build-root.txt");
    std::vector<uint8_t> bytes;
    if (!readWholeFile(pointer, bytes) || bytes.empty()) {
        return;
    }
    std::wstring text;
    for (size_t i = 0; i + 1 < bytes.size(); i += 2) {
        text.push_back(static_cast<wchar_t>(bytes[i] | (bytes[i + 1] << 8)));
    }
    while (!text.empty() && (text.back() == L'\r' || text.back() == L'\n' || text.back() == L' ')) {
        text.pop_back();
    }
    if (text.empty()) {
        return;
    }
    const std::wstring cache = joinPath(text, L"CMakeCache.txt");
    std::vector<uint8_t> cacheBytes;
    if (!readWholeFile(cache, cacheBytes)) {
        return;
    }
    std::string narrow(cacheBytes.begin(), cacheBytes.end());
    const std::string needle = "CMAKE_HOME_DIRECTORY:INTERNAL=" + std::string(installDirectory.begin(), installDirectory.end());
    if (narrow.find(needle) == std::string::npos) {
        logLine("the build folder %s does not belong to this installation, it is kept.", utf8(text).c_str());
        return;
    }
    logLine("removing the build folder: %s", utf8(text).c_str());
    removeTree(text);
}

int runUninstall(const Options& options) {
    std::wstring installDirectory = options.uninstallFrom;
    if (installDirectory.empty()) {
        const std::wstring self = exePath();
        const size_t slash = self.find_last_of(L"\\");
        installDirectory = slash == std::wstring::npos ? std::wstring() : self.substr(0, slash);
    }
    while (installDirectory.size() > 1 && (installDirectory.back() == L'\\' || installDirectory.back() == L'/')) {
        installDirectory.pop_back();
    }
    if (installDirectory.empty() || !isDirectory(installDirectory)) {
        logLine("ERROR: the install folder was not found: %s", utf8(installDirectory).c_str());
        return 1;
    }
    logLine("removing: %s", utf8(installDirectory).c_str());

    std::vector<std::wstring> names;
    if (!readUninstallList(joinPath(installDirectory, L"uninstall.lst"), names)) {
        logLine("ERROR: the uninstall list is missing: %s", utf8(installDirectory).c_str());
        return 1;
    }
    for (const std::wstring& name : names) {
        if (!isSafeRelativePath(name)) {
            continue;
        }
        const std::wstring full = joinPath(installDirectory, name);
        if (!isUnder(full, installDirectory)) {
            continue;
        }
        SetFileAttributesW(full.c_str(), FILE_ATTRIBUTE_NORMAL);
        DeleteFileW(full.c_str());
        removeEmptyDirectories(installDirectory, name);
    }
    // The folders the installer created, when they are empty now.
    const wchar_t* folders[] = { L"launcher\\bin", L"launcher", L"docs", L"games", L"tools", L"engine\\patches",
                                 L"engine" };
    for (const wchar_t* folder : folders) {
        const std::wstring full = joinPath(installDirectory, folder);
        if (isDirectory(full)) {
            RemoveDirectoryW(full.c_str());
        }
    }

    // The shortcuts and the Apps entry.
    std::wstring programs;
    if (knownFolder(FOLDERID_Programs, programs)) {
        DeleteFileW(joinPath(programs, L"God of War Native PC.lnk").c_str());
    }
    std::wstring desktop;
    if (knownFolder(FOLDERID_Desktop, desktop)) {
        DeleteFileW(joinPath(desktop, L"God of War Launcher.lnk").c_str());
    }
    unregisterUninstall();

    if (options.purge) {
        purgeBuildFolder(installDirectory);
    }

    // The uninstaller removes itself once the process is gone.
    const std::wstring self = exePath();
    const std::wstring command = L"cmd.exe /c ping 127.0.0.1 -n 3 >nul & del /q \"" + self + L"\"";
    STARTUPINFOW startup{};
    startup.cb = sizeof(startup);
    PROCESS_INFORMATION process{};
    wchar_t mutableCommand[2048];
    _snwprintf_s(mutableCommand, sizeof(mutableCommand) / sizeof(wchar_t), _TRUNCATE, L"%s", command.c_str());
    if (CreateProcessW(nullptr, mutableCommand, nullptr, nullptr, FALSE, CREATE_NO_WINDOW, nullptr, nullptr, &startup,
                       &process)) {
        CloseHandle(process.hThread);
        CloseHandle(process.hProcess);
    }
    logLine("OK: removed. The game data in the data folder was kept.");
    showResult(L"God of War Native PC", L"Removed.\nThe game data in the data folder was kept.", options.silent);
    return 0;
}

// ---------------------------------------------------------------------------------------------------
// entry point
// ---------------------------------------------------------------------------------------------------

void printUsage() {
    printf("God of War Native PC setup\n");
    printf("  gow-setup.exe --pack <stage dir> <output exe>   build the release setup\n");
    printf("  gow-setup.exe [--dir <folder>] [/S]              install for the current user\n");
    printf("  gow-setup.exe /uninstall [/uninstall-from <dir>] [/purge]\n");
    printf("      remove an installed copy\n");
}

}  // namespace

int wmain(int argc, wchar_t** argv) {
    Options options;
    for (int i = 1; i < argc; ++i) {
        const std::wstring argument = argv[i];
        if (argument == L"--pack") {
            if (i + 2 >= argc) {
                logLine("ERROR: --pack needs the stage directory and the output file.");
                return 1;
            }
            return packStage(argv[i + 1], argv[i + 2]);
        }
        if (argument == L"--dir" && i + 1 < argc) {
            options.directory = argv[++i];
            continue;
        }
        if (argument.rfind(L"--dir=", 0) == 0) {
            options.directory = argument.substr(6);
            continue;
        }
        if (argument.rfind(L"/D=", 0) == 0) {
            options.directory = argument.substr(3);
            continue;
        }
        if (argument == L"/S" || argument == L"--silent") {
            options.silent = true;
            continue;
        }
        if (argument == L"/uninstall" || argument == L"--uninstall") {
            options.uninstall = true;
            continue;
        }
        if (argument == L"/uninstall-from" && i + 1 < argc) {
            options.uninstallFrom = argv[++i];
            options.uninstall = true;
            continue;
        }
        if (argument == L"/purge") {
            options.purge = true;
            continue;
        }
        if (argument == L"--help" || argument == L"-h" || argument == L"/?") {
            printUsage();
            return 0;
        }
        logLine("ERROR: unknown argument: %s", utf8(argument).c_str());
        printUsage();
        return 1;
    }

    if (options.uninstall) {
        return runUninstall(options);
    }

    const HRESULT com = CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED);
    const int result = installPayload(exePath(), options);
    if (SUCCEEDED(com)) {
        CoUninitialize();
    }
    return result;
}
