const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const html=fs.readFileSync(__dirname+'/index.html','utf8');
function load(ctx,start,end){const a=html.indexOf(start),b=html.indexOf(end,a+start.length);assert(a>=0&&b>a,`Missing source markers: ${start}, ${end}`);vm.runInContext(html.slice(a,b),ctx)}
module.exports={html,load,vm,assert};
