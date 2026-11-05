// Exercise production shader ownership with driver creation/compile/link failures.
#include "gs_shader_program.h"
#include <cstdlib>
#include <set>

using namespace GSGL;
namespace {
int failure = 0, creations = 0, links = 0;
std::set<GLuint> shaders, programs;
void check(bool value) { if (!value) std::abort(); }
Api api()
{
    Api g{};
    g.CreateShader = [](GLenum) -> GLuint {
        const GLuint id = ++creations;
        if ((failure == 1 && id == 1) || (failure == 3 && id == 2)) return 0;
        shaders.insert(id); return id;
    };
    g.ShaderSource = [](GLuint id, GLsizei count, const GLchar *const *parts, const GLint *) {
        check(shaders.count(id) && count > 0 && parts[0]);
    };
    g.CompileShader = [](GLuint id) { check(shaders.count(id)); };
    g.GetShaderiv = [](GLuint id, GLenum name, GLint *ok) {
        check(name == kCompileStatus);
        *ok = !((failure == 2 && id == 1) || (failure == 4 && id == 2));
    };
    g.GetShaderInfoLog = [](GLuint, GLsizei, GLsizei *, GLchar *log) { log[0] = 0; };
    g.DeleteShader = [](GLuint id) { check(shaders.erase(id) == 1); };
    g.CreateProgram = []() -> GLuint {
        if (failure == 5) return 0;
        programs.insert(3); return 3;
    };
    g.AttachShader = [](GLuint p, GLuint s) { check(programs.count(p) && shaders.count(s)); };
    g.LinkProgram = [](GLuint p) { check(programs.count(p)); ++links; };
    g.GetProgramiv = [](GLuint p, GLenum name, GLint *ok) {
        check(programs.count(p) && name == kLinkStatus); *ok = failure != 6;
    };
    g.GetProgramInfoLog = [](GLuint, GLsizei, GLsizei *, GLchar *log) { log[0] = 0; };
    g.DeleteProgram = [](GLuint p) { check(programs.erase(p) == 1); };
    return g;
}
}
int main()
{
    const Api g = api();
    for (failure = 0; failure <= 6; ++failure)
    {
        creations = links = 0;
        const GLuint program = BuildRasterProgram(g, {"vertex"}, {"head", "body"});
        check(shaders.empty());
        check(program == (failure ? 0u : 3u));
        check(links == (failure == 0 || failure == 6 ? 1 : 0));
        if (program) g.DeleteProgram(program);
        check(programs.empty());
    }
    std::puts("shader lifecycle: success and six driver failure paths passed");
}
