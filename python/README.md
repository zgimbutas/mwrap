# MWrap — Python version

A pure Python drop-in replacement for the C++
[mwrap](https://github.com/zgimbutas/mwrap) MEX interface generator.
No C/C++ compilation is required — only a Python interpreter.
The runtime support library (`mwrap_support.c`) is also bundled and
can be easily adjusted. This port is **experimental** and tracks the
C++ version's functionality.

## Requirements

- Python 3.6+
- No external dependencies (uses only the standard library)

## Usage

```bash
python/mwrap -mex outputmex -c outputmex.c -m output.m input.mw
python3 python/mwrap -mex outputmex -c outputmex.c -m output.m input.mw
```

Key flags:

| Flag | Description |
|------|-------------|
| `-mex name` | MATLAB MEX function name |
| `-c file.c` | Generate C/C++ MEX gateway file |
| `-m file.m` | Generate MATLAB stub file |
| `-mb` | Generate `.m` files from `@` redirections |
| `-list` | List files from `@` redirections |
| `-catch` | Enable C++ exception handling |
| `-c99complex` | Support C99 complex types |
| `-cppcomplex` | Support C++ complex types |
| `-i8` | Promote `int`/`long` to 64-bit |
| `-gpu` | Support MATLAB `gpuArray` |

## Module overview

| File | Role |
|------|------|
| `mwrap` | Entry point and argument parsing |
| `mwrap_lexer.py` | Tokenizer for `.mw` files |
| `mwrap_parser.py` | Recursive-descent parser producing an AST |
| `mwrap_ast.py` | AST node types and `MwrapContext` |
| `mwrap_typecheck.py` | Type validation |
| `mwrap_cgen.py` | MEX C/C++ code generator |
| `mwrap_mgen.py` | MATLAB `.m` stub generator |
| `mwrap_support.c` | Runtime support library embedded in generated MEX files |

## License

MIT License — see [COPYING](COPYING) for details.
