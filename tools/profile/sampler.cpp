// Sampling profiler for the running game (Windows x64): every millisecond it suspends each thread of the process,
// reads its instruction pointer and resumes it; at the end it resolves the addresses with the executable's PDB
// (build with build.cmd -Pdb) and prints, per thread, the functions where the samples landed (self time).
//
// build (pinned llvm-mingw bin on PATH): clang++ -O2 -std=c++20 -static tools/profile/sampler.cpp -ldbghelp -lwinmm -o sampler.exe
// usage: sampler.exe <pid | exe name> <seconds> [delay seconds] [top N]
//        SAMPLER_LINES=<text>: also the source lines of the functions whose name contains <text>
//        SAMPLER_STACKS=<frames>: also walk that many caller frames per sample and print the callers (inclusive)
#define NOMINMAX
#include <windows.h>
#include <dbghelp.h>
#include <tlhelp32.h>
#include <algorithm>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <map>
#include <string>
#include <thread>
#include <unordered_map>
#include <vector>

static DWORD findProcess(const char *arg)
{
    if (const DWORD pid = std::strtoul(arg, nullptr, 10))
        return pid;
    HANDLE snap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
    PROCESSENTRY32 pe{sizeof(pe)};
    DWORD found = 0;
    for (BOOL ok = Process32First(snap, &pe); ok; ok = Process32Next(snap, &pe))
        if (_stricmp(pe.szExeFile, arg) == 0)
            found = pe.th32ProcessID;
    CloseHandle(snap);
    return found;
}

static std::vector<DWORD> threadsOf(DWORD pid)
{
    std::vector<DWORD> ids;
    HANDLE snap = CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0);
    THREADENTRY32 te{sizeof(te)};
    for (BOOL ok = Thread32First(snap, &te); ok; ok = Thread32Next(snap, &te))
        if (te.th32OwnerProcessID == pid)
            ids.push_back(te.th32ThreadID);
    CloseHandle(snap);
    return ids;
}

static std::string threadName(HANDLE h, DWORD id)
{
    using GetDesc = HRESULT(WINAPI *)(HANDLE, PWSTR *);
    static auto getDesc = reinterpret_cast<GetDesc>(GetProcAddress(GetModuleHandleA("kernel32.dll"), "GetThreadDescription"));
    std::string name;
    PWSTR w = nullptr;
    if (getDesc && SUCCEEDED(getDesc(h, &w)) && w)
    {
        char buf[256] = {};
        WideCharToMultiByte(CP_UTF8, 0, w, -1, buf, sizeof(buf), nullptr, nullptr);
        name = buf;
        LocalFree(w);
    }
    return name.empty() ? "thread " + std::to_string(id) : name + " (" + std::to_string(id) + ")";
}

int main(int argc, char **argv)
{
    if (argc < 3)
    {
        std::fprintf(stderr, "usage: sampler <pid|exe> <seconds> [delay] [top]\n");
        return 2;
    }
    const DWORD pid = findProcess(argv[1]);
    if (!pid)
    {
        std::fprintf(stderr, "process not found: %s\n", argv[1]);
        return 1;
    }
    const double seconds = std::atof(argv[2]);
    const double delay = argc > 3 ? std::atof(argv[3]) : 0.0;
    const int top = argc > 4 ? std::atoi(argv[4]) : 25;
    HANDLE proc = OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, FALSE, pid);
    if (!proc)
    {
        std::fprintf(stderr, "OpenProcess failed (%lu)\n", GetLastError());
        return 1;
    }
    const int stackFrames = std::getenv("SAMPLER_STACKS") ? std::atoi(std::getenv("SAMPLER_STACKS")) : 0;
    std::this_thread::sleep_for(std::chrono::duration<double>(delay));
    SymSetOptions(SYMOPT_UNDNAME | SYMOPT_DEFERRED_LOADS);
    SymInitialize(proc, nullptr, TRUE); // after the delay (modules loaded); the unwinder needs their function tables
    timeBeginPeriod(1);

    struct Thread
    {
        HANDLE h;
        std::string name;
        std::unordered_map<DWORD64, unsigned> hits;
        std::unordered_map<DWORD64, unsigned> callers; // return addresses seen in the walked frames
        unsigned samples = 0;
    };
    std::map<DWORD, Thread> threads;
    const auto end = std::chrono::steady_clock::now() + std::chrono::duration<double>(seconds);
    unsigned rounds = 0;
    while (std::chrono::steady_clock::now() < end)
    {
        if ((rounds++ & 255) == 0) // pick up threads created meanwhile
            for (DWORD id : threadsOf(pid))
                if (!threads.count(id))
                    if (HANDLE h = OpenThread(THREAD_SUSPEND_RESUME | THREAD_GET_CONTEXT | THREAD_QUERY_LIMITED_INFORMATION, FALSE, id))
                        threads[id] = Thread{h, threadName(h, id)};
        for (auto &[id, t] : threads)
        {
            if (SuspendThread(t.h) == static_cast<DWORD>(-1))
                continue;
            CONTEXT c{};
            c.ContextFlags = stackFrames ? CONTEXT_FULL : CONTEXT_CONTROL;
            if (GetThreadContext(t.h, &c))
            {
                ++t.hits[c.Rip];
                ++t.samples;
                STACKFRAME64 f{};
                f.AddrPC.Offset = c.Rip; f.AddrPC.Mode = AddrModeFlat;
                f.AddrStack.Offset = c.Rsp; f.AddrStack.Mode = AddrModeFlat;
                f.AddrFrame.Offset = c.Rbp; f.AddrFrame.Mode = AddrModeFlat;
                for (int depth = 0; stackFrames && depth <= stackFrames; ++depth)
                {
                    if (!StackWalk64(IMAGE_FILE_MACHINE_AMD64, proc, t.h, &f, &c, nullptr, SymFunctionTableAccess64, SymGetModuleBase64, nullptr) || !f.AddrPC.Offset)
                        break;
                    if (depth)
                        ++t.callers[f.AddrPC.Offset];
                }
            }
            ResumeThread(t.h);
        }
        Sleep(1);
    }
    timeEndPeriod(1);

    SymRefreshModuleList(proc);
    std::vector<Thread *> order;
    for (auto &[id, t] : threads)
        if (t.samples)
            order.push_back(&t);
    std::sort(order.begin(), order.end(), [](auto *a, auto *b) { return a->samples > b->samples; });
    alignas(SYMBOL_INFO) char symBuf[sizeof(SYMBOL_INFO) + 512];
    for (Thread *t : order)
    {
        std::unordered_map<std::string, unsigned> byFunc, byCaller;
        for (auto &[addr, n] : t->callers)
        {
            auto *sym = reinterpret_cast<SYMBOL_INFO *>(symBuf);
            sym->SizeOfStruct = sizeof(SYMBOL_INFO);
            sym->MaxNameLen = 511;
            DWORD64 disp = 0;
            byCaller[SymFromAddr(proc, addr, &disp, sym) ? std::string(sym->Name) : std::string("?")] += n;
        }
        for (auto &[addr, n] : t->hits)
        {
            auto *sym = reinterpret_cast<SYMBOL_INFO *>(symBuf);
            sym->SizeOfStruct = sizeof(SYMBOL_INFO);
            sym->MaxNameLen = 511;
            DWORD64 disp = 0;
            std::string name;
            if (SymFromAddr(proc, addr, &disp, sym))
                name = sym->Name;
            else
            {
                IMAGEHLP_MODULE64 mod{sizeof(mod)};
                name = SymGetModuleInfo64(proc, addr, &mod) ? std::string(mod.ModuleName) + "!?" : "?";
            }
            byFunc[name] += n;
        }
        std::vector<std::pair<unsigned, std::string>> rows;
        for (auto &[name, n] : byFunc)
            rows.emplace_back(n, name);
        std::sort(rows.rbegin(), rows.rend());
        std::printf("\n== %s: %u samples\n", t->name.c_str(), t->samples);
        for (int i = 0; i < top && i < static_cast<int>(rows.size()); ++i)
            std::printf("%6.2f%%  %s\n", 100.0 * rows[i].first / t->samples, rows[i].second.c_str());
        if (!byCaller.empty())
        {
            std::vector<std::pair<unsigned, std::string>> callers;
            for (auto &[name, n] : byCaller)
                callers.emplace_back(n, name);
            std::sort(callers.rbegin(), callers.rend());
            for (int i = 0; i < top && i < static_cast<int>(callers.size()); ++i)
                std::printf("   caller %6.2f%%  %s\n", 100.0 * callers[i].first / t->samples, callers[i].second.c_str());
        }
        // SAMPLER_LINES=<text>: for functions whose name contains it, the source lines where the samples landed
        if (const char *want = std::getenv("SAMPLER_LINES"))
        {
            std::unordered_map<std::string, unsigned> byLine;
            for (auto &[addr, n] : t->hits)
            {
                auto *sym = reinterpret_cast<SYMBOL_INFO *>(symBuf);
                sym->SizeOfStruct = sizeof(SYMBOL_INFO);
                sym->MaxNameLen = 511;
                DWORD64 disp = 0;
                if (!SymFromAddr(proc, addr, &disp, sym) || !std::strstr(sym->Name, want))
                    continue;
                IMAGEHLP_LINE64 line{sizeof(line)};
                DWORD lineDisp = 0;
                std::string key = SymGetLineFromAddr64(proc, addr, &lineDisp, &line)
                                      ? std::string(std::strrchr(line.FileName, '\\') ? std::strrchr(line.FileName, '\\') + 1 : line.FileName) + ":" + std::to_string(line.LineNumber)
                                      : std::string(sym->Name) + "+?";
                byLine[key] += n;
            }
            std::vector<std::pair<unsigned, std::string>> lines;
            for (auto &[key, n] : byLine)
                lines.emplace_back(n, key);
            std::sort(lines.rbegin(), lines.rend());
            for (int i = 0; i < 40 && i < static_cast<int>(lines.size()); ++i)
                std::printf("   line %6.2f%%  %s\n", 100.0 * lines[i].first / t->samples, lines[i].second.c_str());
        }
    }
    return 0;
}
