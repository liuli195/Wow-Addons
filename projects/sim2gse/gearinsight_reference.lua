-- Host-only exporter. The input has already passed the table-literal gate.
local env = {}
local chunk = assert(loadfile(arg[1]))
setfenv(chunk, env)
local remaining = 5000000
debug.sethook(function()
    remaining = remaining - 1000
    if remaining <= 0 then error('reference instruction limit') end
end, '', 1000)
chunk()
local root = assert(env.GearInsightRotation, 'missing reference table')['DEATHKNIGHT/UNHOLY']
assert(type(root) == 'table' and root.specID == 252, 'unsupported reference contract')
local rows, visited = {}, 0
local function walk(node, path, context, depth)
    visited = visited + 1
    assert(visited <= 10000 and depth <= 16, 'reference traversal limit')
    if type(node.seq) == 'table' then
        assert(#rows < 256, 'too many openers')
        rows[#rows + 1] = {path=path, record=node, context=context}
        return
    end
    local nextContext, keys = {}, {}
    for k,v in pairs(context) do nextContext[k] = v end
    for k,v in pairs(node) do
        if type(v) ~= 'table' then nextContext[tostring(k)] = v else keys[#keys + 1] = k end
    end
    table.sort(keys, function(a,b) return tostring(a) < tostring(b) end)
    for _,k in ipairs(keys) do
        if k ~= 'tal' and k ~= 'core' and k ~= 'watch' and k ~= 'coach' and k ~= 'follow' then
            walk(node[k], path .. '/' .. tostring(k), nextContext, depth + 1)
        end
    end
end
walk(root, 'DEATHKNIGHT/UNHOLY', {}, 0)
local function quote(s)
    return '"' .. s:gsub('[%z\1-\31\\"]', function(c)
        if c == '\\' then return '\\\\' end
        if c == '"' then return '\\"' end
        return string.format('\\u%04x', string.byte(c))
    end) .. '"'
end
local function encode(value, depth)
    assert(depth < 32, 'json nesting limit')
    local kind = type(value)
    if kind == 'string' then return quote(value) end
    if kind == 'number' then
        assert(value == value and value ~= math.huge and value ~= -math.huge, 'invalid number')
        return tostring(value)
    end
    if kind == 'boolean' then return tostring(value) end
    assert(kind == 'table', 'unsupported field')
    local array, count = true, 0
    for k in pairs(value) do
        count = count + 1
        if type(k) ~= 'number' or k < 1 or k > #value or k % 1 ~= 0 then array = false end
    end
    array = array and count == #value
    local out = {}
    if array then
        for _,v in ipairs(value) do out[#out + 1] = encode(v, depth + 1) end
    else
        for k,v in pairs(value) do out[#out + 1] = quote(tostring(k)) .. ':' .. encode(v, depth + 1) end
    end
    local text = (array and '[' or '{') .. table.concat(out, ',') .. (array and ']' or '}')
    assert(#text <= 2097152, 'json output limit')
    return text
end
local output = encode(rows, 0)
debug.sethook()
io.write(output)
