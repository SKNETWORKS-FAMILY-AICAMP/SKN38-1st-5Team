import json
from pathlib import Path
import shutil
import subprocess
import unittest


class ParkingFrameTest(unittest.TestCase):
    def test_only_own_frame_and_known_place_can_update_details(self):
        node = shutil.which('node') or '/opt/homebrew/opt/node@24/bin/node'
        path = Path(__file__).resolve().parents[1] / 'assets/parking_frame.js'
        script = '''
import assert from 'node:assert/strict';
import fs from 'node:fs';
const {default:render} = await import('data:text/javascript;base64,' + Buffer.from(fs.readFileSync(PATH,'utf8')).toString('base64'));
let listener, removed=false, updates=[];
globalThis.window={addEventListener:(type,fn)=>listener=fn,removeEventListener:()=>removed=true};
const frame={contentWindow:{},style:{},setAttribute(){},remove(){}};
globalThis.document={createElement:()=>frame};
const cleanup=render({parentElement:{append(){}},data:{html:'<p>map</p>',ids:['allowed']},setStateValue:(key,value)=>updates.push([key,value])});
listener({source:{},data:{type:'chachacha-place',id:'allowed'}});
listener({source:frame.contentWindow,data:{type:'chachacha-place',id:'unknown'}});
listener({source:frame.contentWindow,data:{type:'other',id:'allowed'}});
assert.equal(updates.length,0);
listener({source:frame.contentWindow,data:{type:'chachacha-place',id:'allowed'}});
assert.deepEqual(updates,[['selected_place',{id:'allowed'}]]);
cleanup();assert.equal(removed,true);
'''.replace('PATH', json.dumps(str(path)))
        result = subprocess.run([node, '--input-type=module'], input=script, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
