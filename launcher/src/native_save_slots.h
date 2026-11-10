#pragma once

// Read-only PS2 filesystem/index reader. Never replace a card owned by the IOP.
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <ctime>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

namespace gow_native_saves {
using Bytes = std::vector<uint8_t>;
inline uint32_t word(const Bytes &b, size_t p, size_t n=4) {
    if(p>b.size() || n>b.size()-p) throw std::runtime_error("Truncated card data");
    uint32_t v=0;for(size_t i=0;i<n;++i)v|=uint32_t(b[p+i])<<(8*i);return v;
}
struct Entry {uint32_t mode=0,size=0,cluster=0;std::array<uint8_t,8> time{};};
struct Slot {int slot=0,file=0,location=0,difficulty=0;float seconds=0;std::array<uint8_t,8> time{};std::string zone;};
inline std::string localTime(const std::array<uint8_t,8> &t) {
    const int year=t[6]+(int(t[7])<<8);
    if(year<1970 || year>2099 || !t[5] || t[5]>12 || !t[4] || t[4]>31 || t[3]>23 || t[2]>59 || t[1]>59)return {};
    std::tm clock{};clock.tm_year=year-1900;clock.tm_mon=t[5]-1;clock.tm_mday=t[4];
    clock.tm_hour=t[3];clock.tm_min=t[2];clock.tm_sec=t[1];
#ifdef _WIN32
    auto utc=_mkgmtime(&clock);
#else
    auto utc=timegm(&clock);
#endif
    if(utc<0 || clock.tm_mday!=t[4] || clock.tm_mon!=t[5]-1)return {};
    utc-=9*3600; // PS2 memory-card timestamps use the console RTC's Japan time.
    std::tm local{};
#ifdef _WIN32
    if(localtime_s(&local,&utc))return {};
#else
    if(!localtime_r(&utc,&local))return {};
#endif
    char formatted[32];if(!std::strftime(formatted,sizeof(formatted),"%d/%m/%Y %H:%M:%S",&local))return {};
    return formatted;
}
struct Card {
    Bytes data;uint32_t base=0,end=0;std::vector<uint32_t> fat;
    explicit Card(const Bytes &raw) {
        if(raw.size()==8650752) {
            data.reserve(8388608);
            for(size_t p=0;p<raw.size();p+=528)data.insert(data.end(),raw.begin()+p,raw.begin()+p+512);
        } else data=raw;
        if(data.size()!=8388608 || std::memcmp(data.data(),"Sony PS2 Memory Card Format ",28)!=0 ||
           word(data,40,2)!=512 || word(data,42,2)!=2)throw std::runtime_error("Unsupported memory card");
        base=word(data,52);end=word(data,56);
        if(!base || base>=8192 || !end || end>8192-base)throw std::runtime_error("Invalid allocation bounds");
        uint32_t indirect=word(data,80);
        if(!indirect || indirect>=base)throw std::runtime_error("Invalid indirect FAT");
        for(uint32_t i=0;i<(end+255)/256;++i) {
            uint32_t block=word(data,indirect*1024+i*4);
            if(!block || block>=base)throw std::runtime_error("Invalid FAT");fat.push_back(block);
        }
    }
    Bytes chain(uint32_t cluster,uint32_t size) const {
        if(size>data.size())throw std::runtime_error("Invalid file size");
        Bytes out;out.reserve(size);std::set<uint32_t> seen;
        while(out.size()<size) {
            if(cluster>=end || !seen.insert(cluster).second)throw std::runtime_error("Invalid allocation chain");
            uint32_t next=word(data,fat[cluster/256]*1024+(cluster%256)*4);
            if(!(next&0x80000000))throw std::runtime_error("Unallocated cluster");
            size_t p=(base+cluster)*1024,n=std::min<size_t>(1024,size-out.size());
            out.insert(out.end(),data.begin()+p,data.begin()+p+n);cluster=next&0x7fffffff;
        }return out;
    }
    std::map<std::string,Entry> directory(uint32_t cluster,uint32_t count) const {
        if(!count || count>1024)throw std::runtime_error("Invalid directory length");
        Bytes raw=chain(cluster,count*512);std::map<std::string,Entry> result;
        for(size_t p=0;p<raw.size();p+=512) {
            Entry e;e.mode=word(raw,p,2);if(!(e.mode&0x8000))continue;
            e.size=word(raw,p+4);e.cluster=word(raw,p+16);
            std::copy_n(raw.begin()+p+24,8,e.time.begin());
            std::string name;for(size_t i=0;i<32 && raw[p+64+i];++i)name+=char(raw[p+64+i]);
            if(!result.emplace(name,e).second)throw std::runtime_error("Duplicate directory entry");
        }return result;
    }
    std::vector<Slot> entries(const std::string &name) const {
        uint32_t root=word(data,60);auto entries=directory(root,word(chain(root,512),4));
        auto game=entries.find(name);if(game==entries.end())return {};
        if(!(game->second.mode&0x20))throw std::runtime_error("Invalid game directory");
        auto files=directory(game->second.cluster,game->second.size);auto idx=files.find(name);
        if(idx==files.end() || idx->second.size!=68)throw std::runtime_error("Invalid save index");
        Bytes index=chain(idx->second.cluster,68);std::vector<Slot> result;std::set<int> used;
        for(int i=0;i<4;++i) {
            Slot s;s.slot=i;s.file=int32_t(word(index,i*16));
            if(s.file<0 || word(index,i*16+4)!=0xcafebad1)continue;
            uint32_t bits=word(index,i*16+8);std::memcpy(&s.seconds,&bits,4);
            s.location=int16_t(word(index,i*16+12,2));s.difficulty=index[i*16+14];
            if(s.file>4 || !used.insert(s.file).second || !std::isfinite(s.seconds) || s.seconds<0 || s.seconds>1e9 || s.location<=0 || s.location>99)
                throw std::runtime_error("Invalid save index record");
            auto payload=files.find("data"+std::to_string(s.file)+".bin");
            if(payload==files.end() || !(payload->second.mode&0x10) || payload->second.size!=81920)
                throw std::runtime_error("Missing save payload");
            Bytes bytes=chain(payload->second.cluster,payload->second.size);
            if(word(bytes,0)!=0xcafebad1)throw std::runtime_error("Invalid save payload");
            s.time=payload->second.time;
            for(int j=8;j<16 && bytes[j];++j)s.zone+=char(bytes[j]);
            result.push_back(s);
        }return result;
    }
};
inline std::vector<Slot> read(const std::filesystem::path &path,const std::string &directory) {
    std::ifstream file(path,std::ios::binary|std::ios::ate);
    if(!file)throw std::runtime_error("Cannot open memory card");
    auto size=file.tellg();if(size!=8388608 && size!=8650752)throw std::runtime_error("Unsupported memory card size");
    Bytes data(static_cast<size_t>(size));file.seekg(0);
    if(!file.read(reinterpret_cast<char*>(data.data()),data.size()))throw std::runtime_error("Cannot read memory card");
    return Card(data).entries(directory);
}
}
