import assert from 'node:assert/strict';
import test from 'node:test';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { build } from 'esbuild';
import { chromium } from 'playwright';
import { PNG } from 'pngjs';

// Synthetic solids: a red box and a transparent blue tube. Exercise the actual
// stencil path in WebGL, where material/unit assertions cannot detect filled holes
// or stencil leaking from one part into its neighbor.
test('section caps render opaque stable part colors, empty holes and amber fallback', async t => {
  const entry = fileURLToPath(new URL('../../../../core/src/lib/viewer/sectionCaps.js', import.meta.url));
  const bundle = await build({ stdin: { contents: `
    import * as THREE from 'three';
    import { syncSectionCaps } from ${JSON.stringify(entry)};
    const renderer = new THREE.WebGLRenderer({ stencil: true, preserveDrawingBuffer: true });
    renderer.setSize(600,300); renderer.localClippingEnabled = true;
    document.body.style.margin = '0'; document.body.append(renderer.domElement);
    const scene = new THREE.Scene(); scene.background = new THREE.Color('#ffffff');
    const camera = new THREE.OrthographicCamera(-6,6,3,-3,.1,100);
    camera.position.set(0,0,10); camera.lookAt(0,0,0);
    const shape = new THREE.Shape(); shape.absarc(0,0,2,0,Math.PI*2,false);
    const hole = new THREE.Path(); hole.absarc(0,0,.8,0,Math.PI*2,true); shape.holes.push(hole);
    const ring = new THREE.ExtrudeGeometry(shape,{depth:2,bevelEnabled:false,curveSegments:48}); ring.translate(0,0,-1);
    const records = [new THREE.BoxGeometry(4,4,2),ring].map((geometry,i) => {
      const baseColor = new THREE.Color(i ? '#2266dd' : '#dd3322');
      const material = new THREE.MeshBasicMaterial({color:baseColor,transparent:!!i,opacity:i?.2:1});
      const mesh = new THREE.Mesh(geometry,material); mesh.position.x = i?3:-3; scene.add(mesh);
      return {mesh,material,baseColor};
    });
    const runtime = {THREE,scene,displayRecords:records,modelRadius:7};
    window.draw = (partColors=true, depth=0) => {
      const plane = depth === null ? null : new THREE.Plane(new THREE.Vector3(0,0,-1),depth);
      for (const r of records) r.material.clippingPlanes=plane?[plane]:[];
      syncSectionCaps(runtime,plane,{partColors}); renderer.render(scene,camera);
    };
    window.records=records;
    window.pixel = (x,y) => {
      const out = new Uint8Array(4);
      renderer.getContext().readPixels(Math.round((x+6)*50),Math.round((y+3)*50),1,1,renderer.getContext().RGBA,renderer.getContext().UNSIGNED_BYTE,out);
      return [...out];
    };
    window.draw();
  `, resolveDir: process.cwd(), loader:'js' }, bundle:true, format:'iife', write:false });
  const browser = await chromium.launch({headless:true,args:['--use-angle=swiftshader','--enable-unsafe-swiftshader']});
  t.after(() => browser.close());
  const page = await browser.newPage({viewport:{width:600,height:300}});
  const errors=[]; page.on('pageerror',error=>errors.push(error.message));
  await page.setContent('<!doctype html><body></body>');
  await page.addScriptTag({content:bundle.outputFiles[0].text});
  const pixel = (x,y) => page.evaluate(([x,y])=>window.pixel(x,y),[x,y]);
  const shot = async name => {
    if (process.env.CAP_EVIDENCE_DIR) await page.screenshot({path:join(process.env.CAP_EVIDENCE_DIR,`${name}.png`)});
  };
  await shot('part-colors');
  assert.deepEqual(await pixel(-3,0),[221,51,34,255]);
  assert.deepEqual(await pixel(3,1.4),[34,102,221,255],'transparent part has an opaque blue cap');
  assert.deepEqual(await pixel(3,0),[255,255,255,255],'tube bore remains empty');
  const normal = await page.evaluate(()=>window.records.map(r=>[r.material.color.getHex(),r.material.opacity]));
  await page.evaluate(()=>{ window.records.forEach(r=>r.material.color.set('#ffff00')); window.draw(); });
  assert.deepEqual(await pixel(-3,0),[221,51,34,255],'transient live tint never becomes a cap color');
  await page.evaluate(()=>{ window.records.forEach(r=>r.material.color.copy(r.baseColor)); window.draw(false); });
  await shot('uniform-amber');
  assert.deepEqual(await pixel(-3,0),[233,164,81,255]);
  assert.deepEqual(await pixel(3,1.4),[233,164,81,255]);
  assert.deepEqual(await pixel(3,0),[255,255,255,255]);
  assert.deepEqual(await page.evaluate(()=>window.records.map(r=>[r.material.color.getHex(),r.material.opacity])),normal,'cap modes leave outer materials unchanged');
  await page.evaluate(()=>{ window.draw(); window.records[1].mesh.visible=false; window.draw(); });
  assert.deepEqual(await pixel(3,1.4),[255,255,255,255],'hidden part loses its cap');
  await page.evaluate(()=>{ window.records[1].mesh.visible=true; window.draw(true,2); });
  assert.notDeepEqual(await pixel(3,1.4),[34,102,221,255],'moving beyond the part releases the cap');
  await page.evaluate(()=>window.draw(true,null));
  assert.deepEqual(errors,[]);
});


// This checks the React-to-runtime wiring, separately from the stencil pixels above:
// changing only the checkbox must redraw the cut without moving its plane.
test('the Clip checkbox changes the rendered canvas and preserves its plane', async t => {
  const { serveStepHarness } = await import('../harness/stepScenario.mjs');
  const server = await serveStepHarness(t);
  const {page,pane,errors} = await server.open();
  await page.waitForFunction(()=>window.cadHarness.a.controller?.readState().loading === false);
  await page.evaluate(()=>window.cadHarness.a.controller.setDisplaySettings({clip:{enabled:true,axis:'z',at:0}}));
  await pane.getByRole('button',{name:'Clip',exact:true}).click();
  const checkbox = pane.getByRole('checkbox',{name:'Part colors',exact:true});
  await checkbox.waitFor();
  const canvas = pane.locator('[data-cad-surface] canvas').first();
  const settle = () => page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
  await page.waitForFunction(() => {
    const camera = JSON.stringify(window.__cadCamera());
    const still = window.__lastCamera === camera; window.__lastCamera = camera; return still;
  }, null, {polling:'raf'});
  const frame = async () => PNG.sync.read(await canvas.screenshot({style:'[data-cad-tool-groups], [data-cad-tool-stack], [aria-label="View cube"] { visibility: hidden !important; }'}));
  const differences = (a,b) => {
    let changed=0;
    for(let i=0;i<a.data.length;i+=4) if([0,1,2].some(c=>Math.abs(a.data[i+c]-b.data[i+c])>2)) changed++;
    return changed;
  };
  await settle();
  const before = await frame();
  if (process.env.CAP_EVIDENCE_DIR) await page.screenshot({path:join(process.env.CAP_EVIDENCE_DIR,'upstream-part-colors.png')});
  const plane = await page.evaluate(()=>window.cadHarness.a.controller.readState().display.clip);
  await checkbox.uncheck();
  await page.waitForFunction(()=>window.cadHarness.a.controller.readState().display.clip.partColors === false);
  await settle();
  const amber = await frame();
  if (process.env.CAP_EVIDENCE_DIR) await page.screenshot({path:join(process.env.CAP_EVIDENCE_DIR,'upstream-amber.png')});
  assert.ok(differences(amber,before)>100,'toggling only Part colors must reach the WebGL canvas');
  const after = await page.evaluate(()=>window.cadHarness.a.controller.readState().display.clip);
  assert.deepEqual({...after,partColors:true},{...plane,partColors:true});
  await checkbox.check();
  await settle();
  assert.ok(differences(await frame(),before)<20,'returning to Part colors restores the same cap frame');
  assert.deepEqual(errors,[]);
});
