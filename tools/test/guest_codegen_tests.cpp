// Run the upstream code-generator suite independently of obsolete GS/memory test APIs.
#include "MiniTest.h"
void register_code_generator_tests();
void reset_ps2_test_function_table();
int main() {
    MiniTest::BeforeEach(reset_ps2_test_function_table);
    register_code_generator_tests();
    return MiniTest::Run();
}
