assert(_VERSION == "Lua 5.1", "Tests require Lua 5.1")
assert(loadfile(assert(arg[1], "Missing source file")))
