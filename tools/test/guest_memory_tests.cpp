// Run the complete pinned memory suite through the current native service interfaces.
#include "MiniTest.h"
void register_ps2_memory_tests();
void reset_ps2_test_function_table();
int main() {
    MiniTest::BeforeEach(reset_ps2_test_function_table);
    register_ps2_memory_tests();
    return MiniTest::Run();
}
