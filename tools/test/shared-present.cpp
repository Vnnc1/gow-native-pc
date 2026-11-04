// Exercise the production mailbox with deterministic GL fences, without a GPU.
#undef NDEBUG
#include "gs/gpu/gs_gl.cpp"
#include <cassert>
#include <chrono>
#include <future>
#include <thread>

int main()
{
    using namespace GSGL;
    using namespace std::chrono_literals;
    unsigned polls = 0, releases = 0;
    static unsigned *pollCounter;
    static unsigned *releaseCounter;
    pollCounter = &polls;
    releaseCounter = &releases;
    s_hostApi.ClientWaitSync = [](GLsync fence, GLbitfield flags, GLuint64 timeout) -> GLenum {
        assert(flags == 0 && timeout == 0);
        ++*pollCounter;
        return fence == reinterpret_cast<GLsync>(2) ? kTimeoutExpired : kAlreadySignaled;
    };
    s_hostApi.DeleteSync = [](GLsync) {};
    s_hostApi.FenceSync = [](GLenum, GLbitfield) -> GLsync {
        ++*releaseCounter;
        return reinterpret_cast<GLsync>(3);
    };
    s_hostApi.Flush = [] {};
    s_sharedActive = true;
    GSSharedPresent::Frame frame;
    assert(!GSSharedPresent::Acquire(frame));
    const auto contend = [&](bool available, uint64_t sequence, bool blank) {
        std::promise<void> held, done;
        auto released = done.get_future();
        std::thread producer([&] {
            std::lock_guard<std::mutex> lock(s_sharedMutex);
            held.set_value();
            // A timeout also releases the old blocking implementation so the test fails cleanly.
            released.wait_for(2s);
        });
        held.get_future().wait();
        const unsigned before = polls;
        const auto start = std::chrono::steady_clock::now();
        const bool acquired = GSSharedPresent::Acquire(frame);
        const auto elapsed = std::chrono::steady_clock::now() - start;
        done.set_value();
        producer.join();
        std::printf("publisher-held snapshot=%llu acquire_us=%lld available=%d\n",
            static_cast<unsigned long long>(sequence),
            static_cast<long long>(std::chrono::duration_cast<std::chrono::microseconds>(elapsed).count()), acquired);
        std::fflush(stdout);
        assert(elapsed < 1s && acquired == available && polls == before);
        if (available) assert(frame.sequence == sequence && frame.blank == blank);
    };
    contend(false, 0, false);
    s_sharedSlots[0].frame.sequence = 1;
    s_sharedSlots[0].frame.texture = 11;
    s_sharedSlots[0].frame.width = s_sharedSlots[0].frame.height = 64;
    s_sharedSlots[0].produced = reinterpret_cast<GLsync>(1);
    assert(GSSharedPresent::Acquire(frame) && frame.sequence == 1);
    contend(true, 1, false);
    assert(s_sharedSlots[0].reading && releases == 0 && frame.texture == 11);
    s_sharedSlots[1].frame.sequence = 2;
    s_sharedSlots[1].produced = reinterpret_cast<GLsync>(2); // Not GPU-complete.
    assert(GSSharedPresent::Acquire(frame) && frame.sequence == 1);
    s_sharedSlots[2].frame.sequence = 3;
    s_sharedSlots[2].frame.blank = true;
    s_sharedSlots[2].produced = reinterpret_cast<GLsync>(1);
    assert(GSSharedPresent::Acquire(frame) && frame.sequence == 3 && frame.blank);
    assert(!s_sharedSlots[0].reading && s_sharedSlots[2].reading && releases == 1);
    contend(true, 3, true); // Blank frames must not resurrect the old texture.
    GSSharedPresent::ShutdownHost();
    assert(!GSSharedPresent::Acquire(frame));
    s_sharedActive = true;
    contend(false, 0, false); // No snapshot survives a host restart.
    s_sharedActive = false;
    std::puts("PASS: shared presentation stays nonblocking under publisher contention; latest completed frame, slot ownership, blank and restart semantics");
}
