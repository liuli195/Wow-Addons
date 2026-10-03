assert(_VERSION == "Lua 5.1", "Tests require Lua 5.1")
assert(arg[1], "Missing source file")
for i = 1, #arg do
    assert(loadfile(arg[i]))
end
