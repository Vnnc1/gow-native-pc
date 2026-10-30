// gow-native-pc installer ("gow-native-pc-setup.exe"): one file that installs the release package (the launcher with its
// Qt DLLs + tools, games, engine, docs: data/_package/gow-native-pc) for the current user, without administrator rights.
// Pick a folder, Install, Open launcher. The same program is the uninstaller (copied as uninstall.exe, listed in
// Windows' Apps) and the packer that makes the setup:
//   gow-setup.exe --pack <package folder> <out.exe>    appends the package, LZMS-compressed, to a copy of itself
// Layout of a packed exe: [this program][blocks: u32 raw size, u32 packed size, bytes]...[Footer]. The raw stream is
// u32 file count, per file u16 path length + UTF-16 relative path + u64 size, then the contents in the same order.
// The window is drawn with GDI+ in the launcher's colours (launcher/qml/Tema.qml). Built by tools/pipeline/build.ps1
// (stage installer).
#define NOMINMAX
#include <windows.h>

#include <algorithm>
namespace Gdiplus
{
using std::max;
using std::min;
}
#include <compressapi.h>
#include <gdiplus.h>
#include <shlobj.h>
#include <shobjidl.h>

#include <atomic>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <memory>
#include <string>
#include <thread>
#include <vector>

#ifndef GOW_VERSION
#define GOW_VERSION "1.0.0"
#endif

namespace fs = std::filesystem;
using namespace Gdiplus;

namespace
{
// ------------------------------------------------------------------------------------------------ payload format
#pragma pack(push, 1)
struct Footer
{
    char magic[8];
    uint64_t offset; // where the blocks start (= size of the program itself)
    uint64_t raw;    // size of the uncompressed stream
    uint32_t blocks;
    uint32_t version;
};
#pragma pack(pop)
constexpr char kMagic[8] = {'G', 'O', 'W', 'S', 'E', 'T', 'U', 'P'};
constexpr size_t kBlock = 16u << 20;

const wchar_t *const kProduct = L"God of War Native PC";
const wchar_t *const kUninstallKey = L"Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\gow-native-pc";
const wchar_t *const kLauncher = L"launcher\\bin\\gow-launcher.exe";
const wchar_t *const kFolderLink = L"God of War Launcher.lnk"; // same name as the launcher stage's shortcut in a checkout
const wchar_t *const kRepoUrl = L"https://github.com/Vnnc1/gow-native-pc";

std::wstring selfPath()
{
    std::wstring p(32768, L'\0');
    p.resize(GetModuleFileNameW(nullptr, p.data(), static_cast<DWORD>(p.size())));
    return p;
}

bool readAll(const std::wstring &path, std::vector<uint8_t> &out)
{
    HANDLE f = CreateFileW(path.c_str(), GENERIC_READ, FILE_SHARE_READ, nullptr, OPEN_EXISTING, 0, nullptr);
    if (f == INVALID_HANDLE_VALUE)
        return false;
    LARGE_INTEGER size{};
    GetFileSizeEx(f, &size);
    out.resize(static_cast<size_t>(size.QuadPart));
    size_t done = 0;
    while (done < out.size())
    {
        DWORD n = 0;
        const DWORD want = static_cast<DWORD>(std::min<size_t>(out.size() - done, 64u << 20));
        if (!ReadFile(f, out.data() + done, want, &n, nullptr) || n == 0)
            break;
        done += n;
    }
    CloseHandle(f);
    return done == out.size();
}

bool writeAll(const std::wstring &path, const uint8_t *data, size_t size, DWORD *error = nullptr)
{
    HANDLE f = CreateFileW(path.c_str(), GENERIC_WRITE, 0, nullptr, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (f == INVALID_HANDLE_VALUE)
    {
        if (error)
            *error = GetLastError();
        return false;
    }
    size_t done = 0;
    bool ok = true;
    while (done < size && ok)
    {
        DWORD n = 0;
        ok = WriteFile(f, data + done, static_cast<DWORD>(std::min<size_t>(size - done, 64u << 20)), &n, nullptr) && n > 0;
        done += n;
    }
    if (!ok && error)
        *error = GetLastError();
    CloseHandle(f);
    return ok;
}

// The footer of a packed exe, or false for the bare program.
bool footerOf(const std::vector<uint8_t> &exe, Footer &f)
{
    if (exe.size() < sizeof(Footer))
        return false;
    std::memcpy(&f, exe.data() + exe.size() - sizeof(Footer), sizeof(Footer));
    return std::memcmp(f.magic, kMagic, sizeof(kMagic)) == 0 && f.offset < exe.size();
}

void say(const std::string &s) // build log (the packer runs from build.ps1 with redirected output)
{
    DWORD n;
    WriteFile(GetStdHandle(STD_OUTPUT_HANDLE), s.data(), static_cast<DWORD>(s.size()), &n, nullptr);
}

int pack(const std::wstring &dir, const std::wstring &out)
{
    std::vector<uint8_t> self;
    if (!readAll(selfPath(), self))
        return say("cannot read the installer program\n"), 1;
    Footer old{};
    const size_t stub = footerOf(self, old) ? static_cast<size_t>(old.offset) : self.size();

    std::vector<fs::path> files;
    std::error_code ec;
    for (const auto &e : fs::recursive_directory_iterator(dir, ec))
        if (e.is_regular_file())
            files.push_back(e.path());
    if (ec || files.empty())
        return say("no files in the package folder\n"), 1;
    std::sort(files.begin(), files.end());

    std::vector<uint8_t> raw;
    auto put = [&raw](const void *p, size_t n) { raw.insert(raw.end(), static_cast<const uint8_t *>(p), static_cast<const uint8_t *>(p) + n); };
    const uint32_t count = static_cast<uint32_t>(files.size());
    put(&count, 4);
    std::vector<std::vector<uint8_t>> contents(files.size());
    for (size_t i = 0; i < files.size(); ++i)
    {
        const std::wstring rel = fs::relative(files[i], dir).wstring();
        if (!readAll(files[i].wstring(), contents[i]))
            return say("cannot read a package file\n"), 1;
        const uint16_t len = static_cast<uint16_t>(rel.size());
        const uint64_t size = contents[i].size();
        put(&len, 2);
        put(rel.data(), rel.size() * sizeof(wchar_t));
        put(&size, 8);
    }
    for (auto &c : contents)
    {
        put(c.data(), c.size());
        std::vector<uint8_t>().swap(c);
    }

    // LZMS per 16 MB block, four blocks at a time (each compressor takes a lot of memory)
    const size_t blocks = (raw.size() + kBlock - 1) / kBlock;
    std::vector<std::vector<uint8_t>> packed(blocks);
    std::atomic<bool> ok{true};
    for (size_t first = 0; first < blocks; first += 4)
    {
        std::vector<std::thread> workers;
        for (size_t i = first; i < std::min(blocks, first + 4); ++i)
            workers.emplace_back([&, i] {
                COMPRESSOR_HANDLE h = nullptr;
                if (!CreateCompressor(COMPRESS_ALGORITHM_LZMS, nullptr, &h))
                    return void(ok = false);
                const size_t in = std::min(kBlock, raw.size() - i * kBlock);
                SIZE_T need = 0;
                Compress(h, raw.data() + i * kBlock, in, nullptr, 0, &need);
                packed[i].resize(need);
                SIZE_T got = 0;
                if (!Compress(h, raw.data() + i * kBlock, in, packed[i].data(), need, &got))
                    ok = false;
                packed[i].resize(got);
                CloseCompressor(h);
            });
        for (auto &w : workers)
            w.join();
    }
    if (!ok)
        return say("compression failed\n"), 1;

    std::vector<uint8_t> exe(self.begin(), self.begin() + stub);
    for (size_t i = 0; i < blocks; ++i)
    {
        const uint32_t rawSize = static_cast<uint32_t>(std::min(kBlock, raw.size() - i * kBlock));
        const uint32_t packedSize = static_cast<uint32_t>(packed[i].size());
        exe.insert(exe.end(), reinterpret_cast<const uint8_t *>(&rawSize), reinterpret_cast<const uint8_t *>(&rawSize) + 4);
        exe.insert(exe.end(), reinterpret_cast<const uint8_t *>(&packedSize), reinterpret_cast<const uint8_t *>(&packedSize) + 4);
        exe.insert(exe.end(), packed[i].begin(), packed[i].end());
    }
    Footer f{};
    std::memcpy(f.magic, kMagic, sizeof(kMagic));
    f.offset = stub;
    f.raw = raw.size();
    f.blocks = static_cast<uint32_t>(blocks);
    f.version = 1;
    exe.insert(exe.end(), reinterpret_cast<const uint8_t *>(&f), reinterpret_cast<const uint8_t *>(&f) + sizeof(f));
    if (!writeAll(out, exe.data(), exe.size()))
        return say("cannot write the setup exe\n"), 1;
    say(std::to_string(files.size()) + " files, " + std::to_string(raw.size() >> 20) + " MB -> " + std::to_string(exe.size() >> 20) + " MB\n");
    return 0;
}

// ------------------------------------------------------------------------------------------------ texts
int g_lang = 0; // 0 en, 1 pt, 2 es (Windows display language)
enum Txt
{
    tSubtitle, tFolder, tChange, tDesktop, tInfo, tInstall, tUpdate, tCancel, tInstalling, tUnpacking, tDone, tDoneText,
    tOpen, tClose, tFailed, tRetry, tLocked, tNoWrite, tBroken, tPick, tUninstall, tUninstallTitle, tKeep, tRemoving,
    tRemoved, tRemovedKept, tRemovedAll, tRunning, tCount
};
const wchar_t *const kTexts[tCount][3] = {
    {L"NATIVE PC  \u00b7  SETUP", L"NATIVE PC  \u00b7  INSTALADOR", L"NATIVE PC  \u00b7  INSTALADOR"},
    {L"INSTALL FOLDER", L"PASTA DE INSTALA\u00c7\u00c3O", L"CARPETA DE INSTALACI\u00d3N"},
    {L"Change", L"Alterar", L"Cambiar"},
    {L"Desktop shortcut", L"Atalho na \u00e1rea de trabalho", L"Acceso directo en el escritorio"},
    {L"%1 MB. The game itself is built later by the launcher, from your own ISO.",
     L"%1 MB. O jogo em si \u00e9 compilado depois pelo launcher, a partir da sua ISO.",
     L"%1 MB. El juego se compila despu\u00e9s con el lanzador, a partir de tu ISO."},
    {L"INSTALL", L"INSTALAR", L"INSTALAR"},
    {L"UPDATE", L"ATUALIZAR", L"ACTUALIZAR"},
    {L"Cancel", L"Cancelar", L"Cancelar"},
    {L"INSTALLING", L"INSTALANDO", L"INSTALANDO"},
    {L"Unpacking\u2026", L"Descompactando\u2026", L"Descomprimiendo\u2026"},
    {L"Installed", L"Instalado", L"Instalado"},
    {L"Open the launcher: it downloads the runtime, takes your ISO and builds the game.",
     L"Abra o launcher: ele baixa o runtime, recebe sua ISO e compila o jogo.",
     L"Abre el lanzador: descarga el runtime, recibe tu ISO y compila el juego."},
    {L"OPEN LAUNCHER", L"ABRIR LAUNCHER", L"ABRIR LANZADOR"},
    {L"Close", L"Fechar", L"Cerrar"},
    {L"Installation failed", L"A instala\u00e7\u00e3o falhou", L"La instalaci\u00f3n fall\u00f3"},
    {L"TRY AGAIN", L"TENTAR DE NOVO", L"REINTENTAR"},
    {L"A file is in use: close the launcher and the game, then try again.",
     L"Um arquivo est\u00e1 em uso: feche o launcher e o jogo e tente de novo.",
     L"Un archivo est\u00e1 en uso: cierra el lanzador y el juego e int\u00e9ntalo de nuevo."},
    {L"This folder needs administrator rights: choose a folder of yours.",
     L"Esta pasta exige administrador: escolha uma pasta sua.",
     L"Esta carpeta necesita administrador: elige una carpeta tuya."},
    {L"The installer is damaged: download it again.", L"O instalador est\u00e1 corrompido: baixe de novo.",
     L"El instalador est\u00e1 da\u00f1ado: desc\u00e1rgalo de nuevo."},
    {L"Choose the install folder", L"Escolha a pasta de instala\u00e7\u00e3o", L"Elige la carpeta de instalaci\u00f3n"},
    {L"REMOVE", L"REMOVER", L"DESINSTALAR"},
    {L"Remove from this PC", L"Remover deste PC", L"Quitar de este PC"},
    {L"Keep game data (saves, prepared discs, built game)", L"Manter dados do jogo (saves, discos preparados, jogo compilado)",
     L"Conservar datos del juego (partidas, discos preparados, juego compilado)"},
    {L"REMOVING", L"REMOVENDO", L"QUITANDO"},
    {L"Removed", L"Removido", L"Quitado"},
    {L"Your game data stayed in the data folder.", L"Seus dados do jogo ficaram na pasta data.", L"Tus datos del juego quedaron en la carpeta data."},
    {L"Everything was removed.", L"Tudo foi removido.", L"Se quit\u00f3 todo."},
    {L"The launcher or the game is open: close it first.", L"O launcher ou o jogo est\u00e1 aberto: feche antes.",
     L"El lanzador o el juego est\u00e1 abierto: ci\u00e9rralo antes."},
};
std::wstring T(Txt t) { return kTexts[t][g_lang]; }

// ------------------------------------------------------------------------------------------------ state
enum class State { Ready, Working, Done, Failed, UninstallReady, UninstallDone };
enum Hit { hNone, hClose, hMinimize, hChange, hToggle, hPrimary, hSecondary, hCount };
enum : UINT { kMsgProgress = WM_APP + 1, kMsgDone = WM_APP + 2, kTimer = 1 };

HWND g_wnd;
UINT g_dpi = 96;
State g_state = State::Ready;
bool g_uninstall = false;      // this run removes an installation
std::wstring g_dir;            // install folder
bool g_existing = false;       // g_dir already holds an installation
bool g_toggle = false;         // desktop shortcut (off unless the user turns it on) / keep game data (on)
std::wstring g_message;        // Failed / UninstallDone text
std::wstring g_file;           // file being written
int g_target = 0, g_shown = 0; // progress in 1/1000 (worker target, eased display)
uint64_t g_rawSize = 0;
RECT g_hit[hCount];
Hit g_hover = hNone;
ULONGLONG g_tick0;
std::thread g_worker;
std::vector<uint8_t> g_self;
Footer g_footer{};
bool g_payload = false;
bool g_ok = false; // result of the last worker (silent mode)

float F(float v) { return v * static_cast<float>(g_dpi) / 96.f; }
Color C(uint32_t rgb, BYTE a = 255) { return Color(a, (rgb >> 16) & 255, (rgb >> 8) & 255, rgb & 255); }
std::wstring knownFolder(REFKNOWNFOLDERID id)
{
    PWSTR p = nullptr;
    std::wstring s;
    if (SUCCEEDED(SHGetKnownFolderPath(id, 0, nullptr, &p)))
        s = p;
    CoTaskMemFree(p);
    return s;
}
bool exists(const std::wstring &p) { return GetFileAttributesW(p.c_str()) != INVALID_FILE_ATTRIBUTES; }
// Absolute path with the \\?\ prefix: package paths under a deep folder pass Windows' 260-character limit.
std::wstring longPath(const std::wstring &p)
{
    if (p.rfind(L"\\\\?\\", 0) == 0 || p.size() < 3 || p[1] != L':')
        return p;
    std::wstring out = L"\\\\?\\" + p;
    std::replace(out.begin() + 4, out.end(), L'/', L'\\');
    return out;
}
bool isInstall(const std::wstring &dir) { return exists(dir + L"\\games\\gow1\\game.toml") && exists(dir + L"\\" + kLauncher); }

std::wstring regString(const wchar_t *name)
{
    wchar_t buf[2048] = {};
    DWORD size = sizeof(buf);
    if (RegGetValueW(HKEY_CURRENT_USER, kUninstallKey, name, RRF_RT_REG_SZ, nullptr, buf, &size) == ERROR_SUCCESS)
        return buf;
    return {};
}

void setText(HKEY k, const wchar_t *name, const std::wstring &v)
{
    RegSetValueExW(k, name, 0, REG_SZ, reinterpret_cast<const BYTE *>(v.c_str()), static_cast<DWORD>((v.size() + 1) * sizeof(wchar_t)));
}

bool shortcut(const std::wstring &lnk, const std::wstring &target, const std::wstring &workDir)
{
    IShellLinkW *link = nullptr;
    if (FAILED(CoCreateInstance(CLSID_ShellLink, nullptr, CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&link))))
        return false;
    link->SetPath(target.c_str());
    link->SetWorkingDirectory(workDir.c_str());
    link->SetIconLocation(target.c_str(), 0);
    link->SetDescription(kProduct);
    IPersistFile *file = nullptr;
    bool ok = false;
    if (SUCCEEDED(link->QueryInterface(IID_PPV_ARGS(&file))))
    {
        ok = SUCCEEDED(file->Save(lnk.c_str(), TRUE));
        file->Release();
    }
    link->Release();
    return ok;
}
std::wstring startMenuLink() { return knownFolder(FOLDERID_Programs) + L"\\" + kProduct + L".lnk"; }
std::wstring desktopLink() { return knownFolder(FOLDERID_Desktop) + L"\\" + kProduct + L".lnk"; }

void progress(int permille, const std::wstring &file)
{
    PostMessageW(g_wnd, kMsgProgress, permille, reinterpret_cast<LPARAM>(new std::wstring(file)));
}
void finish(bool ok, const std::wstring &message)
{
    g_ok = ok;
    g_message = message;
    PostMessageW(g_wnd, kMsgDone, ok, reinterpret_cast<LPARAM>(new std::wstring(message)));
}

// ------------------------------------------------------------------------------------------------ install / remove
void installWorker(std::wstring dir, bool desktop)
{
    CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED);
    std::error_code ec;
    fs::create_directories(dir, ec);
    const std::wstring probe = dir + L"\\.write-test";
    if (!writeAll(probe, reinterpret_cast<const uint8_t *>("x"), 1))
        return finish(false, T(tNoWrite)), CoUninitialize();
    DeleteFileW(probe.c_str());

    // unpack (0-30 %)
    std::vector<uint8_t> raw(static_cast<size_t>(g_footer.raw));
    size_t at = static_cast<size_t>(g_footer.offset), out = 0;
    DECOMPRESSOR_HANDLE h = nullptr;
    CreateDecompressor(COMPRESS_ALGORITHM_LZMS, nullptr, &h);
    for (uint32_t b = 0; b < g_footer.blocks; ++b)
    {
        uint32_t rawSize, packedSize;
        std::memcpy(&rawSize, g_self.data() + at, 4);
        std::memcpy(&packedSize, g_self.data() + at + 4, 4);
        at += 8;
        SIZE_T got = 0;
        if (!h || out + rawSize > raw.size() || at + packedSize > g_self.size() ||
            !Decompress(h, g_self.data() + at, packedSize, raw.data() + out, rawSize, &got) || got != rawSize)
        {
            if (h)
                CloseDecompressor(h);
            return finish(false, T(tBroken)), CoUninitialize();
        }
        at += packedSize;
        out += rawSize;
        progress(static_cast<int>(300 * (b + 1) / g_footer.blocks), T(tUnpacking));
    }
    CloseDecompressor(h);

    // files (30-97 %)
    struct Entry { std::wstring path; uint64_t size; };
    std::vector<Entry> entries;
    size_t p = 0;
    uint32_t count;
    std::memcpy(&count, raw.data(), 4);
    p = 4;
    for (uint32_t i = 0; i < count; ++i)
    {
        uint16_t len;
        std::memcpy(&len, raw.data() + p, 2);
        p += 2;
        Entry e{std::wstring(reinterpret_cast<const wchar_t *>(raw.data() + p), len), 0};
        p += len * sizeof(wchar_t);
        std::memcpy(&e.size, raw.data() + p, 8);
        p += 8;
        entries.push_back(std::move(e));
    }
    std::wstring list;
    uint64_t written = 0;
    for (const Entry &e : entries)
    {
        const std::wstring target = longPath(dir + L"\\" + e.path);
        fs::create_directories(fs::path(target).parent_path(), ec);
        DWORD err = 0;
        if (!writeAll(target, raw.data() + p, static_cast<size_t>(e.size), &err))
            return finish(false, err == ERROR_SHARING_VIOLATION || err == ERROR_ACCESS_DENIED ? T(tLocked) : T(tFailed) + L": " + e.path),
                   CoUninitialize();
        p += static_cast<size_t>(e.size);
        written += e.size + 4096;
        list += e.path + L"\r\n";
        progress(300 + static_cast<int>(670 * written / (g_footer.raw + 4096ull * entries.size())), e.path);
    }

    // uninstaller, Windows' Apps entry, shortcuts (97-100 %)
    writeAll(dir + L"\\uninstall.exe", g_self.data(), static_cast<size_t>(g_footer.offset));
    const std::string bom = "\xFF\xFE";
    std::vector<uint8_t> lst(bom.begin(), bom.end());
    lst.insert(lst.end(), reinterpret_cast<const uint8_t *>(list.data()), reinterpret_cast<const uint8_t *>(list.data() + list.size()));
    writeAll(dir + L"\\uninstall.lst", lst.data(), lst.size());
    HKEY k;
    if (RegCreateKeyExW(HKEY_CURRENT_USER, kUninstallKey, 0, nullptr, 0, KEY_WRITE, nullptr, &k, nullptr) == ERROR_SUCCESS)
    {
        const std::wstring launcher = dir + L"\\" + kLauncher;
        setText(k, L"DisplayName", kProduct);
        setText(k, L"DisplayVersion", L"" GOW_VERSION);
        setText(k, L"Publisher", L"gow-native-pc");
        setText(k, L"InstallLocation", dir);
        setText(k, L"DisplayIcon", launcher);
        setText(k, L"UninstallString", L"\"" + dir + L"\\uninstall.exe\" /uninstall");
        setText(k, L"URLInfoAbout", kRepoUrl);
        const DWORD one = 1, kb = static_cast<DWORD>(g_footer.raw / 1024);
        RegSetValueExW(k, L"NoModify", 0, REG_DWORD, reinterpret_cast<const BYTE *>(&one), 4);
        RegSetValueExW(k, L"NoRepair", 0, REG_DWORD, reinterpret_cast<const BYTE *>(&one), 4);
        RegSetValueExW(k, L"EstimatedSize", 0, REG_DWORD, reinterpret_cast<const BYTE *>(&kb), 4);
        RegCloseKey(k);
    }
    const std::wstring launcher = dir + L"\\" + kLauncher, launcherDir = dir + L"\\launcher\\bin";
    shortcut(startMenuLink(), launcher, launcherDir);
    shortcut(dir + L"\\" + kFolderLink, launcher, launcherDir); // in the install folder, next to uninstall.exe
    if (desktop)
        shortcut(desktopLink(), launcher, launcherDir);
    else
        DeleteFileW(desktopLink().c_str());
    progress(1000, L"");
    finish(true, L"");
    CoUninitialize();
}

// True when <build>/CMakeCache.txt was configured from <dir>/engine/runtime (CMAKE_HOME_DIRECTORY, forward slashes).
bool buildBelongsTo(const std::wstring &build, const std::wstring &dir)
{
    std::vector<uint8_t> cache;
    if (!readAll(build + L"\\CMakeCache.txt", cache))
        return false;
    std::wstring want = dir + L"\\engine\\runtime";
    std::replace(want.begin(), want.end(), L'\\', L'/');
    const int n = WideCharToMultiByte(CP_UTF8, 0, want.c_str(), -1, nullptr, 0, nullptr, nullptr);
    std::string key(n > 0 ? n - 1 : 0, ' ');
    WideCharToMultiByte(CP_UTF8, 0, want.c_str(), -1, key.data(), n, nullptr, nullptr);
    const std::string text(cache.begin(), cache.end());
    const size_t at = text.find("CMAKE_HOME_DIRECTORY:INTERNAL=");
    if (at == std::string::npos)
        return false;
    const size_t start = at + 30, end = text.find_first_of("\r\n", start);
    std::string home = text.substr(start, end == std::string::npos ? std::string::npos : end - start);
    auto lower = [](std::string s) { std::transform(s.begin(), s.end(), s.begin(), [](unsigned char c) { return static_cast<char>(tolower(c)); }); return s; };
    return lower(home).rfind(lower(key), 0) == 0;
}

void removeWorker(std::wstring dir, bool keep)
{
    std::vector<uint8_t> lst;
    std::vector<std::wstring> files;
    if (readAll(dir + L"\\uninstall.lst", lst) && lst.size() > 2)
    {
        std::wstring all(reinterpret_cast<const wchar_t *>(lst.data() + 2), (lst.size() - 2) / sizeof(wchar_t));
        for (size_t a = 0, b; a < all.size(); a = b + 2)
        {
            b = all.find(L"\r\n", a);
            if (b == std::wstring::npos)
                b = all.size();
            if (b > a)
                files.push_back(all.substr(a, b - a));
        }
    }
    std::vector<std::wstring> dirs;
    for (size_t i = 0; i < files.size(); ++i)
    {
        const std::wstring f = longPath(dir + L"\\" + files[i]);
        DeleteFileW(f.c_str());
        for (fs::path d = fs::path(files[i]).parent_path(); !d.empty(); d = d.parent_path())
            dirs.push_back(longPath(dir + L"\\" + d.wstring()));
        progress(static_cast<int>(800 * (i + 1) / std::max<size_t>(1, files.size())), files[i]);
    }
    std::sort(dirs.begin(), dirs.end(), [](const std::wstring &a, const std::wstring &b) { return a.size() > b.size(); });
    for (const auto &d : dirs)
        RemoveDirectoryW(d.c_str()); // only empty ones
    DeleteFileW((dir + L"\\uninstall.lst").c_str());
    DeleteFileW((dir + L"\\uninstall.exe").c_str());
    DeleteFileW((dir + L"\\" + kFolderLink).c_str());
    std::error_code ec;
    if (!keep)
    {
        // data/ (discs, saves, recompiled code, VU1 recordings), the downloaded runtime and the build folders
        // (tools/pipeline/build.ps1) — a build folder only when its CMake cache belongs to this installation, so a
        // build made from another copy (a development checkout) is never touched
        std::wstring build = L"C:\\gow-build"; // this copy's build folder: data\build-root.txt (build.ps1)
        std::vector<uint8_t> chosen;
        if (readAll(dir + L"\\data\\build-root.txt", chosen) && !chosen.empty())
        {
            std::wstring s(chosen.begin(), chosen.end()); // an ASCII path such as C:\gow-build-1a2b3c4d
            s.erase(s.find_last_not_of(L" \r\n\t") + 1);
            if (!s.empty())
                build = s;
        }
        fs::remove_all(dir + L"\\data", ec);
        fs::remove_all(dir + L"\\engine\\runtime", ec);
        for (const std::wstring &folder : {build, build + L"-dev"})
            if (buildBelongsTo(folder, dir))
                fs::remove_all(folder, ec);
    }
    progress(900, L"");
    RemoveDirectoryW((dir + L"\\engine").c_str());
    RemoveDirectoryW(dir.c_str());
    DeleteFileW(startMenuLink().c_str());
    DeleteFileW(desktopLink().c_str());
    RegDeleteTreeW(HKEY_CURRENT_USER, kUninstallKey);
    progress(1000, L"");
    finish(true, keep ? T(tRemovedKept) : T(tRemovedAll));
}

bool gameRunning(const std::wstring &dir)
{
    // the launcher locks its exe while it runs; the game runner is in the build folder
    HANDLE f = CreateFileW((dir + L"\\" + kLauncher).c_str(), GENERIC_WRITE, 0, nullptr, OPEN_EXISTING, 0, nullptr);
    if (f == INVALID_HANDLE_VALUE)
        return GetLastError() == ERROR_SHARING_VIOLATION;
    CloseHandle(f);
    return false;
}

void start()
{
    if (g_worker.joinable())
        g_worker.join();
    if (gameRunning(g_dir))
    {
        g_message = T(tRunning);
        g_state = g_uninstall ? State::UninstallReady : State::Failed;
        if (g_uninstall)
            MessageBoxW(g_wnd, g_message.c_str(), kProduct, MB_ICONINFORMATION);
        InvalidateRect(g_wnd, nullptr, FALSE);
        return;
    }
    g_state = State::Working;
    g_target = g_shown = 0;
    g_file.clear();
    SetTimer(g_wnd, kTimer, 16, nullptr);
    if (g_uninstall)
        g_worker = std::thread(removeWorker, g_dir, g_toggle);
    else
        g_worker = std::thread(installWorker, g_dir, g_toggle);
    InvalidateRect(g_wnd, nullptr, FALSE);
}

void pickFolder()
{
    IFileOpenDialog *dlg = nullptr;
    if (FAILED(CoCreateInstance(CLSID_FileOpenDialog, nullptr, CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&dlg))))
        return;
    DWORD opts = 0;
    dlg->GetOptions(&opts);
    dlg->SetOptions(opts | FOS_PICKFOLDERS | FOS_FORCEFILESYSTEM | FOS_PATHMUSTEXIST);
    dlg->SetTitle(T(tPick).c_str());
    IShellItem *start = nullptr;
    const std::wstring parent = fs::path(g_dir).parent_path().wstring();
    if (SUCCEEDED(SHCreateItemFromParsingName(parent.c_str(), nullptr, IID_PPV_ARGS(&start))))
    {
        dlg->SetFolder(start);
        start->Release();
    }
    IShellItem *item = nullptr;
    PWSTR path = nullptr;
    if (SUCCEEDED(dlg->Show(g_wnd)) && SUCCEEDED(dlg->GetResult(&item)) && SUCCEEDED(item->GetDisplayName(SIGDN_FILESYSPATH, &path)))
    {
        std::wstring chosen = path;
        while (chosen.size() > 3 && chosen.back() == L'\\')
            chosen.pop_back();
        // a folder of its own unless the chosen one is empty or already an installation
        std::error_code ec;
        const bool empty = fs::is_empty(chosen, ec);
        if (!isInstall(chosen) && !empty && _wcsicmp(fs::path(chosen).filename().c_str(), L"gow-native-pc") != 0)
            chosen = (chosen.back() == L'\\' ? chosen : chosen + L"\\") + L"gow-native-pc";
        g_dir = chosen;
        g_existing = isInstall(g_dir);
    }
    CoTaskMemFree(path);
    if (item)
        item->Release();
    dlg->Release();
    InvalidateRect(g_wnd, nullptr, FALSE);
}

// ------------------------------------------------------------------------------------------------ drawing
void roundRect(GraphicsPath &p, RectF r, float rad)
{
    const float d = rad * 2;
    p.AddArc(r.X, r.Y, d, d, 180, 90);
    p.AddArc(r.GetRight() - d, r.Y, d, d, 270, 90);
    p.AddArc(r.GetRight() - d, r.GetBottom() - d, d, d, 0, 90);
    p.AddArc(r.X, r.GetBottom() - d, d, d, 90, 90);
    p.CloseFigure();
}

void text(Graphics &g, const std::wstring &s, const wchar_t *face, float px, Color c, RectF r, StringAlignment h = StringAlignmentNear,
          StringAlignment v = StringAlignmentNear, StringTrimming trim = StringTrimmingNone, int style = FontStyleRegular)
{
    Font font(face, F(px), style, UnitPixel);
    StringFormat fmt;
    fmt.SetAlignment(h);
    fmt.SetLineAlignment(v);
    fmt.SetTrimming(trim);
    if (trim != StringTrimmingNone)
        fmt.SetFormatFlags(StringFormatFlagsNoWrap);
    SolidBrush b(c);
    g.DrawString(s.c_str(), -1, &font, r, &fmt, &b);
}

RECT toRect(RectF r) { return RECT{static_cast<LONG>(r.X), static_cast<LONG>(r.Y), static_cast<LONG>(r.GetRight()), static_cast<LONG>(r.GetBottom())}; }

// Crimson blade with the top-right corner cut, like the launcher's Play button.
void primary(Graphics &g, RectF r, const std::wstring &label)
{
    g_hit[hPrimary] = toRect(r);
    const bool hover = g_hover == hPrimary;
    const float cut = F(14);
    GraphicsPath p;
    PointF pts[] = {{r.X, r.Y}, {r.GetRight() - cut, r.Y}, {r.GetRight(), r.Y + cut}, {r.GetRight(), r.GetBottom()}, {r.X, r.GetBottom()}};
    p.AddPolygon(pts, 5);
    LinearGradientBrush br(PointF(r.X, r.Y), PointF(r.GetRight(), r.GetBottom()), hover ? C(0xff4a36) : C(0xe0352a), hover ? C(0xc42619) : C(0xa51d15));
    g.FillPath(&br, &p);
    SolidBrush line(C(0xffffff, 64));
    g.FillRectangle(&line, r.X, r.GetBottom() - F(2), r.Width, F(2));
    text(g, label, L"Segoe UI Black", 15, C(0xffffff), r, StringAlignmentCenter, StringAlignmentCenter);
}

void secondary(Graphics &g, RectF r, const std::wstring &label)
{
    g_hit[hSecondary] = toRect(r);
    const bool hover = g_hover == hSecondary;
    GraphicsPath p;
    roundRect(p, r, F(6));
    SolidBrush fill(hover ? C(0x262a32) : C(0x1c1f26));
    g.FillPath(&fill, &p);
    Pen pen(hover ? C(0x4a505c) : C(0x3a404c), F(1));
    g.DrawPath(&pen, &p);
    text(g, label, L"Segoe UI Semibold", 13.5f, C(0xeef0f4), r, StringAlignmentCenter, StringAlignmentCenter);
}

void toggleRow(Graphics &g, float x, float y, float w, const std::wstring &label)
{
    RectF pill(x, y, F(40), F(22));
    g_hit[hToggle] = toRect(RectF(x, y - F(4), w, F(30)));
    GraphicsPath p;
    roundRect(p, pill, F(11));
    SolidBrush fill(g_toggle ? C(0xe0402f) : C(0x15171c));
    g.FillPath(&fill, &p);
    Pen pen(g_toggle ? C(0xe0402f) : (g_hover == hToggle ? C(0x3a404c) : C(0x252932)), F(1));
    g.DrawPath(&pen, &p);
    SolidBrush knob(g_toggle ? C(0xffffff) : C(0xa9afba));
    const float k = F(16);
    g.FillEllipse(&knob, g_toggle ? pill.GetRight() - k - F(3) : pill.X + F(3), pill.Y + F(3), k, k);
    text(g, label, L"Segoe UI", 13.5f, C(0xeef0f4), RectF(x + F(54), y - F(4), w - F(54), F(30)), StringAlignmentNear, StringAlignmentCenter,
         StringTrimmingEllipsisCharacter);
}

void paint(HDC dc)
{
    RECT rc;
    GetClientRect(g_wnd, &rc);
    const float W = static_cast<float>(rc.right), H = static_cast<float>(rc.bottom);
    Bitmap buffer(rc.right, rc.bottom, PixelFormat32bppPARGB);
    Graphics g(&buffer);
    g.SetSmoothingMode(SmoothingModeAntiAlias);
    g.SetTextRenderingHint(TextRenderingHintClearTypeGridFit);
    g.SetPixelOffsetMode(PixelOffsetModeHalf);
    for (RECT &r : g_hit)
        r = RECT{};

    // background: graphite with a crimson glow low on the right, and the two tattoo blades
    LinearGradientBrush bg(PointF(0, 0), PointF(0, H), C(0x101217), C(0x0b0c0f));
    g.FillRectangle(&bg, 0.f, 0.f, W, H);
    GraphicsPath glowPath;
    glowPath.AddEllipse(W * 0.45f, H * 0.55f, W * 0.9f, H * 1.0f);
    PathGradientBrush glow(&glowPath);
    glow.SetCenterColor(C(0x5a1410, 150));
    Color edge = C(0x000000, 0);
    INT n = 1;
    glow.SetSurroundColors(&edge, &n);
    g.FillPath(&glow, &glowPath);
    SolidBrush blade(C(0xc62a20, 40)), blade2(C(0xc62a20, 22));
    PointF b1[] = {{W * 0.70f, 0}, {W * 0.84f, 0}, {W * 0.60f, H}, {W * 0.46f, H}};
    PointF b2[] = {{W * 0.90f, 0}, {W * 0.95f, 0}, {W * 0.75f, H}, {W * 0.70f, H}};
    g.FillPolygon(&blade, b1, 4);
    g.FillPolygon(&blade2, b2, 4);

    // window buttons
    const float bw = F(46), bh = F(36);
    g_hit[hMinimize] = toRect(RectF(W - 2 * bw, 0, bw, bh));
    g_hit[hClose] = toRect(RectF(W - bw, 0, bw, bh));
    if (g_hover == hClose)
    {
        SolidBrush red(C(0xc42b1c));
        g.FillRectangle(&red, W - bw, 0.f, bw, bh);
    }
    else if (g_hover == hMinimize)
    {
        SolidBrush light(C(0xffffff, 31));
        g.FillRectangle(&light, W - 2 * bw, 0.f, bw, bh);
    }
    Pen glyph(C(0xdfe2e8), F(1.1f));
    const float cx = W - bw / 2, cy = bh / 2, s = F(5);
    g.DrawLine(&glyph, cx - s, cy - s, cx + s, cy + s);
    g.DrawLine(&glyph, cx + s, cy - s, cx - s, cy + s);
    g.DrawLine(&glyph, W - 1.5f * bw - s, cy, W - 1.5f * bw + s, cy);

    // brand
    const float m = F(36);
    RectF logo(m, F(34), F(46), F(46));
    GraphicsPath lp;
    roundRect(lp, logo, F(10));
    LinearGradientBrush lb(PointF(0, logo.Y), PointF(0, logo.GetBottom()), C(0xe0352a), C(0x7a1610));
    g.FillPath(&lb, &lp);
    text(g, L"\u03a9", L"Segoe UI Black", 27, C(0xffffff), RectF(logo.X, logo.Y - F(2), logo.Width, logo.Height), StringAlignmentCenter,
         StringAlignmentCenter);
    text(g, L"GOD OF WAR", L"Segoe UI Black", 24, C(0xffffff), RectF(m + F(60), F(30), W, F(34)));
    text(g, T(tSubtitle), L"Segoe UI Semibold", 11, C(0xff8a75), RectF(m + F(62), F(62), W, F(18)));

    const float bodyY = F(116), cw = W - 2 * m;
    const RectF btn1(m, H - F(36) - F(52), F(230), F(52)), btn2(m + F(244), H - F(36) - F(52), F(130), F(52));
    switch (g_state)
    {
    case State::Ready:
    case State::UninstallReady:
    {
        if (g_uninstall)
        {
            text(g, T(tUninstallTitle), L"Segoe UI Black", 26, C(0xffffff), RectF(m, bodyY, cw, F(40)));
            text(g, g_dir, L"Segoe UI", 13, C(0xa9afba), RectF(m, bodyY + F(44), cw, F(22)), StringAlignmentNear, StringAlignmentNear,
                 StringTrimmingEllipsisPath);
            toggleRow(g, m, bodyY + F(96), cw, T(tKeep));
            primary(g, btn1, T(tUninstall));
        }
        else
        {
            text(g, T(tFolder), L"Segoe UI Semibold", 11, C(0x6a707c), RectF(m, bodyY, cw, F(18)));
            RectF box(m, bodyY + F(22), cw, F(44));
            GraphicsPath bp;
            roundRect(bp, box, F(8));
            SolidBrush boxFill(C(0x15171c, 235));
            g.FillPath(&boxFill, &bp);
            Pen boxPen(g_hover == hChange ? C(0x3a404c) : C(0x252932), F(1));
            g.DrawPath(&boxPen, &bp);
            const float changeW = F(96);
            text(g, g_dir, L"Segoe UI", 13.5f, C(0xeef0f4), RectF(box.X + F(14), box.Y, box.Width - changeW - F(14), box.Height),
                 StringAlignmentNear, StringAlignmentCenter, StringTrimmingEllipsisPath);
            RectF change(box.GetRight() - changeW, box.Y, changeW, box.Height);
            g_hit[hChange] = toRect(change);
            text(g, T(tChange), L"Segoe UI Semibold", 13.5f, g_hover == hChange ? C(0xffffff) : C(0xff8a75), change, StringAlignmentCenter,
                 StringAlignmentCenter);
            toggleRow(g, m, bodyY + F(90), cw, T(tDesktop));
            std::wstring info = T(tInfo);
            info.replace(info.find(L"%1"), 2, std::to_wstring(g_rawSize >> 20));
            text(g, info, L"Segoe UI", 12.5f, C(0x6a707c), RectF(m, bodyY + F(128), cw, F(40)));
            primary(g, btn1, T(g_existing ? tUpdate : tInstall));
        }
        secondary(g, btn2, T(tCancel));
        break;
    }
    case State::Working:
    {
        text(g, T(g_uninstall ? tRemoving : tInstalling), L"Segoe UI Semibold", 11, C(0x6a707c), RectF(m, bodyY, cw, F(18)));
        text(g, std::to_wstring(g_shown / 10) + L"%", L"Segoe UI Black", 52, C(0xffffff), RectF(m - F(3), bodyY + F(12), cw, F(70)));
        text(g, g_file, L"Segoe UI", 12, C(0xa9afba), RectF(m, bodyY + F(86), cw, F(20)), StringAlignmentNear, StringAlignmentNear,
             StringTrimmingEllipsisPath);
        const RectF track(m, bodyY + F(124), cw, F(6));
        SolidBrush trackFill(C(0x1c1f26));
        g.FillRectangle(&trackFill, track);
        const float fillW = track.Width * g_shown / 1000.f;
        if (fillW > 0)
        {
            LinearGradientBrush fill(PointF(track.X - 1, 0), PointF(track.X + fillW + 1, 0), C(0xa51d15), C(0xff4a36));
            g.FillRectangle(&fill, track.X, track.Y, fillW, track.Height);
            // a light sweeping over the filled part
            const float sweep = F(120);
            const float pos = std::fmod((GetTickCount64() - g_tick0) / 1400.f, 1.f) * (fillW + sweep) - sweep;
            const float x0 = std::max(track.X, track.X + pos), x1 = std::min(track.X + fillW, track.X + pos + sweep);
            if (x1 > x0)
            {
                LinearGradientBrush shine(PointF(track.X + pos - 1, 0), PointF(track.X + pos + sweep + 1, 0), C(0xffffff, 0), C(0xffffff, 0));
                Color cols[] = {C(0xffffff, 0), C(0xffffff, 120), C(0xffffff, 0)};
                REAL at[] = {0.f, 0.5f, 1.f};
                shine.SetInterpolationColors(cols, at, 3);
                g.FillRectangle(&shine, x0, track.Y, x1 - x0, track.Height);
            }
        }
        break;
    }
    case State::Done:
    case State::UninstallDone:
    {
        RectF badge(m, bodyY + F(4), F(40), F(40));
        SolidBrush ok(C(0x5fd08a));
        g.FillEllipse(&ok, badge);
        Pen tick(C(0x0b0c0f), F(3.5f));
        tick.SetLineCap(LineCapRound, LineCapRound, DashCapRound);
        PointF tp[] = {{badge.X + F(11), badge.Y + F(21)}, {badge.X + F(17.5f), badge.Y + F(27)}, {badge.X + F(29), badge.Y + F(14)}};
        g.DrawLines(&tick, tp, 3);
        text(g, T(g_state == State::Done ? tDone : tRemoved), L"Segoe UI Black", 30, C(0xffffff), RectF(m + F(54), bodyY - F(2), cw, F(50)));
        text(g, g_state == State::Done ? T(tDoneText) : g_message, L"Segoe UI", 14, C(0xa9afba), RectF(m, bodyY + F(62), cw, F(60)));
        if (g_state == State::Done)
        {
            primary(g, btn1, T(tOpen));
            secondary(g, btn2, T(tClose));
        }
        else
            primary(g, btn1, T(tClose));
        break;
    }
    case State::Failed:
        text(g, T(tFailed), L"Segoe UI Black", 26, C(0xffffff), RectF(m, bodyY, cw, F(40)));
        text(g, g_message, L"Segoe UI", 14, C(0xff6450), RectF(m, bodyY + F(48), cw, F(60)));
        if (g_payload)
            primary(g, btn1, T(tRetry));
        secondary(g, btn2, T(tClose));
        break;
    }

    Pen frame(C(0x252932), 1);
    g.DrawRectangle(&frame, 0.f, 0.f, W - 1, H - 1);
    Graphics screen(dc);
    screen.DrawImage(&buffer, 0, 0);
}

Hit hitAt(POINT p)
{
    for (int h = hClose; h < hCount; ++h)
        if (PtInRect(&g_hit[h], p))
            return static_cast<Hit>(h);
    return hNone;
}

void click(Hit h)
{
    switch (h)
    {
    case hClose:
        PostMessageW(g_wnd, WM_CLOSE, 0, 0);
        break;
    case hMinimize:
        ShowWindow(g_wnd, SW_MINIMIZE);
        break;
    case hChange:
        pickFolder();
        break;
    case hToggle:
        g_toggle = !g_toggle;
        InvalidateRect(g_wnd, nullptr, FALSE);
        break;
    case hPrimary:
        if (g_state == State::Ready || g_state == State::UninstallReady || g_state == State::Failed)
            start();
        else if (g_state == State::Done)
        {
            const std::wstring exe = g_dir + L"\\" + kLauncher;
            ShellExecuteW(nullptr, L"open", exe.c_str(), nullptr, (g_dir + L"\\launcher\\bin").c_str(), SW_SHOWNORMAL);
            PostMessageW(g_wnd, WM_CLOSE, 0, 0);
        }
        else if (g_state == State::UninstallDone)
            PostMessageW(g_wnd, WM_CLOSE, 0, 0);
        break;
    case hSecondary:
        PostMessageW(g_wnd, WM_CLOSE, 0, 0);
        break;
    default:
        break;
    }
}

LRESULT CALLBACK proc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp)
{
    switch (msg)
    {
    case WM_PAINT:
    {
        PAINTSTRUCT ps;
        HDC dc = BeginPaint(hwnd, &ps);
        paint(dc);
        EndPaint(hwnd, &ps);
        return 0;
    }
    case WM_ERASEBKGND:
        return 1;
    case WM_NCHITTEST:
    {
        POINT p{static_cast<short>(LOWORD(lp)), static_cast<short>(HIWORD(lp))};
        ScreenToClient(hwnd, &p);
        if (hitAt(p) == hNone && p.y < F(100))
            return HTCAPTION; // drag the window by its top
        return HTCLIENT;
    }
    case WM_MOUSEMOVE:
    {
        Hit h = hitAt({static_cast<short>(LOWORD(lp)), static_cast<short>(HIWORD(lp))});
        if (g_state == State::Working && h > hMinimize)
            h = hNone; // only the window buttons react while working
        if (h != g_hover)
        {
            g_hover = h;
            InvalidateRect(hwnd, nullptr, FALSE);
        }
        TRACKMOUSEEVENT t{sizeof(t), TME_LEAVE, hwnd, 0};
        TrackMouseEvent(&t);
        return 0;
    }
    case WM_MOUSELEAVE:
        g_hover = hNone;
        InvalidateRect(hwnd, nullptr, FALSE);
        return 0;
    case WM_SETCURSOR:
        if (LOWORD(lp) == HTCLIENT && g_hover >= hChange)
        {
            SetCursor(LoadCursorW(nullptr, IDC_HAND));
            return TRUE;
        }
        break;
    case WM_LBUTTONUP:
    {
        const Hit h = hitAt({static_cast<short>(LOWORD(lp)), static_cast<short>(HIWORD(lp))});
        if (g_state != State::Working || h == hMinimize)
            click(h);
        return 0;
    }
    case WM_KEYDOWN:
        if (wp == VK_RETURN && g_state != State::Working)
            click(hPrimary);
        else if (wp == VK_ESCAPE && g_state != State::Working)
            PostMessageW(hwnd, WM_CLOSE, 0, 0);
        return 0;
    case WM_TIMER:
        g_shown += std::max(1, (g_target - g_shown) / 6);
        g_shown = std::min(g_shown, g_target);
        InvalidateRect(hwnd, nullptr, FALSE);
        return 0;
    case kMsgProgress:
    {
        std::unique_ptr<std::wstring> file(reinterpret_cast<std::wstring *>(lp));
        g_target = static_cast<int>(wp);
        if (!file->empty())
            g_file = *file;
        return 0;
    }
    case kMsgDone:
    {
        std::unique_ptr<std::wstring> message(reinterpret_cast<std::wstring *>(lp));
        KillTimer(hwnd, kTimer);
        if (g_worker.joinable())
            g_worker.join();
        g_message = *message;
        g_shown = g_target;
        if (wp)
        {
            g_state = g_uninstall ? State::UninstallDone : State::Done;
            g_existing = !g_uninstall;
        }
        else
            g_state = State::Failed;
        InvalidateRect(hwnd, nullptr, FALSE);
        return 0;
    }
    case WM_CLOSE:
        if (g_state == State::Working)
            return 0;
        DestroyWindow(hwnd);
        return 0;
    case WM_DESTROY:
        PostQuitMessage(0);
        return 0;
    }
    return DefWindowProcW(hwnd, msg, wp, lp);
}
} // namespace

int WINAPI wWinMain(HINSTANCE inst, HINSTANCE, PWSTR, int)
{
    int argc = 0;
    wchar_t **argv = CommandLineToArgvW(GetCommandLineW(), &argc);
    if (argc >= 4 && wcscmp(argv[1], L"--pack") == 0)
        return pack(argv[2], argv[3]);

    const LANGID lang = PRIMARYLANGID(GetUserDefaultUILanguage());
    g_lang = lang == LANG_PORTUGUESE ? 1 : (lang == LANG_SPANISH ? 2 : 0);
    CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED);

    // silent use (and tests): /S [/D=<folder>] installs; /uninstall-from <folder> /S [/purge] removes
    bool silent = false, purge = false;
    std::wstring silentDir;
    for (int i = 1; i < argc; ++i)
    {
        silent |= _wcsicmp(argv[i], L"/S") == 0;
        purge |= _wcsicmp(argv[i], L"/purge") == 0;
        if (_wcsnicmp(argv[i], L"/D=", 3) == 0)
            silentDir = argv[i] + 3;
    }

    std::wstring selfToDelete;
    // uninstall.exe is this program without the package: opened by hand (double-click in the install folder) it
    // removes that installation instead of reporting a damaged installer
    const std::wstring ownDir = fs::path(selfPath()).parent_path().wstring();
    bool bareInInstall = false;
    if (argc == 1 && isInstall(ownDir) && exists(ownDir + L"\\uninstall.lst"))
    {
        std::vector<uint8_t> self;
        Footer f{};
        bareInInstall = readAll(selfPath(), self) && !footerOf(self, f);
    }
    if ((argc >= 2 && _wcsicmp(argv[1], L"/uninstall") == 0) || bareInInstall)
    {
        // run from a copy in %TEMP% so this exe and its folder can be removed
        const std::wstring self = selfPath();
        const std::wstring dir = fs::path(self).parent_path().wstring();
        wchar_t tmp[MAX_PATH];
        GetTempPathW(MAX_PATH, tmp);
        const std::wstring copy = std::wstring(tmp) + L"gow-native-pc-uninstall.exe";
        CopyFileW(self.c_str(), copy.c_str(), FALSE);
        ShellExecuteW(nullptr, L"open", copy.c_str(), (L"/uninstall-from \"" + dir + L"\"").c_str(), nullptr, SW_SHOWNORMAL);
        return 0;
    }
    if (argc >= 3 && _wcsicmp(argv[1], L"/uninstall-from") == 0)
    {
        g_uninstall = true;
        g_dir = argv[2];
        g_state = State::UninstallReady;
        g_toggle = true; // keep game data unless the user turns it off
        selfToDelete = selfPath();
    }
    else
    {
        g_payload = readAll(selfPath(), g_self) && footerOf(g_self, g_footer);
        g_rawSize = g_payload ? g_footer.raw : 0;
        g_dir = regString(L"InstallLocation");
        if (g_dir.empty())
            g_dir = knownFolder(FOLDERID_LocalAppData) + L"\\Programs\\gow-native-pc";
        g_existing = isInstall(g_dir);
        if (!g_payload)
        {
            g_state = State::Failed;
            g_message = T(tBroken);
        }
    }

    if (silent)
    {
        if (g_uninstall)
            removeWorker(g_dir, !purge);
        else if (g_payload)
            installWorker(silentDir.empty() ? g_dir : silentDir, false);
        if (!g_ok)
        {
            const int n = WideCharToMultiByte(CP_UTF8, 0, g_message.c_str(), -1, nullptr, 0, nullptr, nullptr);
            std::string m(n > 0 ? n - 1 : 0, ' ');
            WideCharToMultiByte(CP_UTF8, 0, g_message.c_str(), -1, m.data(), n, nullptr, nullptr);
            say(m + "\n");
        }
        CoUninitialize();
        LocalFree(argv);
        return g_ok ? 0 : 1;
    }

    using SetDpiCtx = BOOL(WINAPI *)(HANDLE);
    if (auto set = reinterpret_cast<SetDpiCtx>(GetProcAddress(GetModuleHandleW(L"user32"), "SetProcessDpiAwarenessContext")))
        set(reinterpret_cast<HANDLE>(-4)); // per-monitor v2
    using GetDpi = UINT(WINAPI *)();
    if (auto get = reinterpret_cast<GetDpi>(GetProcAddress(GetModuleHandleW(L"user32"), "GetDpiForSystem")))
        g_dpi = get();

    GdiplusStartupInput gin;
    ULONG_PTR token;
    GdiplusStartup(&token, &gin, nullptr);
    g_tick0 = GetTickCount64();

    WNDCLASSW wc{};
    wc.style = CS_DROPSHADOW;
    wc.lpfnWndProc = proc;
    wc.hInstance = inst;
    wc.hIcon = LoadIconW(inst, MAKEINTRESOURCEW(1));
    wc.hCursor = LoadCursorW(nullptr, IDC_ARROW);
    wc.lpszClassName = L"GowNativePcSetup";
    RegisterClassW(&wc);
    const int w = static_cast<int>(F(620)), h = static_cast<int>(F(400));
    g_wnd = CreateWindowExW(WS_EX_APPWINDOW, wc.lpszClassName, (std::wstring(kProduct) + L" Setup").c_str(), WS_POPUP | WS_SYSMENU | WS_MINIMIZEBOX,
                            (GetSystemMetrics(SM_CXSCREEN) - w) / 2, (GetSystemMetrics(SM_CYSCREEN) - h) / 2, w, h, nullptr, nullptr, inst, nullptr);
    ShowWindow(g_wnd, SW_SHOW);
    UpdateWindow(g_wnd);

    // screenshots for the docs: GOW_SETUP_CAPTURE=<png> saves the window after it is drawn and quits
    wchar_t capture[MAX_PATH] = {};
    if (GetEnvironmentVariableW(L"GOW_SETUP_CAPTURE", capture, MAX_PATH))
        SetTimer(g_wnd, 2, 700, [](HWND hwnd, UINT, UINT_PTR, DWORD) {
            wchar_t out[MAX_PATH] = {};
            GetEnvironmentVariableW(L"GOW_SETUP_CAPTURE", out, MAX_PATH);
            RECT rc;
            GetClientRect(hwnd, &rc);
            Bitmap shot(rc.right, rc.bottom, PixelFormat32bppARGB);
            {
                Graphics g(&shot);
                HDC dc = g.GetHDC();
                paint(dc);
                g.ReleaseHDC(dc);
            }
            CLSID png;
            UINT num = 0, size = 0;
            GetImageEncodersSize(&num, &size);
            std::vector<uint8_t> buf(size);
            auto *codecs = reinterpret_cast<ImageCodecInfo *>(buf.data());
            GetImageEncoders(num, size, codecs);
            for (UINT i = 0; i < num; ++i)
                if (wcscmp(codecs[i].MimeType, L"image/png") == 0)
                    png = codecs[i].Clsid;
            shot.Save(out, &png, nullptr);
            DestroyWindow(hwnd);
        });

    MSG m;
    while (GetMessageW(&m, nullptr, 0, 0) > 0)
    {
        TranslateMessage(&m);
        DispatchMessageW(&m);
    }
    if (g_worker.joinable())
        g_worker.join();
    GdiplusShutdown(token);
    CoUninitialize();
    if (!selfToDelete.empty())
    {
        // the copy in %TEMP% deletes itself once it has exited
        std::wstring cmd = L"cmd.exe /c ping 127.0.0.1 -n 3 >nul & del /q \"" + selfToDelete + L"\"";
        STARTUPINFOW si{};
        si.cb = sizeof(si);
        si.dwFlags = STARTF_USESHOWWINDOW;
        si.wShowWindow = SW_HIDE;
        PROCESS_INFORMATION pi{};
        if (CreateProcessW(nullptr, cmd.data(), nullptr, nullptr, FALSE, CREATE_NO_WINDOW, nullptr, nullptr, &si, &pi))
        {
            CloseHandle(pi.hThread);
            CloseHandle(pi.hProcess);
        }
    }
    LocalFree(argv);
    return 0;
}
