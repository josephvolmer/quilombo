'use strict';

/* ────────────────────────────────────────────────────────────────────
   QUILOMBO hero — raymarched iridescent chrome.

   A fragment shader on one full-screen triangle: SDF torus knots in a
   twisted domain, marched, shaded with a thin-film interference ramp
   and a fresnel rim. The look (liquid chrome tubes, oily rainbow
   sheen, slow drift) is entirely in the shader.

   Why no three.js here: three is a scene graph, and this scene is one
   quad. It would not author the shader — the shader *is* the effect —
   so it would cost ~167KB gz to replace the ~40 lines of WebGL setup
   below. tsParticles stays for nothing; this replaces it outright.

   Degrades in layers: no WebGL → CSS gradient backdrop stays; reduced
   motion → renders a single still frame; offscreen/hidden → paused.
   ──────────────────────────────────────────────────────────────── */

const VERT = `
attribute vec2 p;
void main() { gl_Position = vec4(p, 0.0, 1.0); }
`;

const FRAG = `
precision highp float;
uniform vec2  iRes;
uniform float iTime;
uniform vec2  iPointer;

// ── rotation helper
mat2 rot(float a){ float c = cos(a), s = sin(a); return mat2(c, -s, s, c); }

// ── signed distance to a torus
float sdTorus(vec3 p, vec2 t){
  vec2 q = vec2(length(p.xz) - t.x, p.y);
  return length(q) - t.y;
}

// smooth union — lets the tubes melt into each other
float smin(float a, float b, float k){
  float h = clamp(0.5 + 0.5 * (b - a) / k, 0.0, 1.0);
  return mix(b, a, h) - k * h * (1.0 - h);
}

// ── the scene: a few tori tumbling through a twisted domain
float map(vec3 p){
  vec3 q = p;
  // slow global twist so the shapes read as liquid rather than rigid
  q.xy *= rot(sin(iTime * 0.09) * 0.18);
  q.xz *= rot(iTime * 0.035);

  float d = 1e9;

  // Three tori parked off-centre, each drifting on its own slow cycle.
  // Nothing crosses the middle: the title lives there.
  vec3 a = q + vec3(-2.45, -0.35 + sin(iTime * 0.21) * 0.32, 0.0);
  a.xy *= rot(iTime * 0.17);
  d = smin(d, sdTorus(a, vec2(1.02, 0.27)), 0.45);

  vec3 b = q + vec3(2.55, 0.75 + cos(iTime * 0.18) * 0.28, -0.3);
  b.yz *= rot(iTime * 0.15 + 1.7);
  d = smin(d, sdTorus(b, vec2(0.88, 0.24)), 0.45);

  vec3 c = q + vec3(0.35, 2.35 + sin(iTime * 0.13) * 0.25, 0.5);
  c.xz *= rot(-iTime * 0.12 + 3.1);
  c.xy *= rot(0.6);
  d = smin(d, sdTorus(c, vec2(0.74, 0.20)), 0.45);

  return d;
}

vec3 normal(vec3 p){
  vec2 e = vec2(0.0015, 0.0);
  return normalize(vec3(
    map(p + e.xyy) - map(p - e.xyy),
    map(p + e.yxy) - map(p - e.yxy),
    map(p + e.yyx) - map(p - e.yyx)));
}


// Procedural environment: dark room with bright streak lights. Chrome is
// almost entirely reflection, so this is what actually shapes the look.
vec3 envMap(vec3 r){
  vec3 c = vec3(0.012, 0.016, 0.022);          // dark room

  // broad horizontal softbox streaks
  float band1 = exp(-pow((r.y - 0.42) * 5.0, 2.0));
  float band2 = exp(-pow((r.y + 0.30) * 6.5, 2.0));
  c += vec3(0.85, 1.00, 0.55) * band1 * 2.4;   // acid key light
  c += vec3(0.30, 0.55, 1.00) * band2 * 1.5;   // azure fill

  // a couple of tight highlights that sweep as the shape turns
  float s1 = pow(max(dot(normalize(r), normalize(vec3( 0.6, 0.7, 0.4))), 0.0), 48.0);
  float s2 = pow(max(dot(normalize(r), normalize(vec3(-0.7, 0.2, 0.6))), 0.0), 64.0);
  c += vec3(1.0) * s1 * 3.2;
  c += vec3(0.75, 0.95, 1.0) * s2 * 2.4;

  return c;
}

// thin-film / oil-slick ramp — the iridescence
vec3 iridescence(float t){
  return 0.55 + 0.45 * cos(6.28318 * (t + vec3(0.0, 0.33, 0.67)));
}

void main(){
  vec2 uv = (gl_FragCoord.xy - 0.5 * iRes) / iRes.y;

  // camera drifts a little with the pointer, so it feels alive
  vec3 ro = vec3(0.0, 0.0, 5.6);
  ro.xy += iPointer * 0.35;
  vec3 rd = normalize(vec3(uv, -1.45));

  float t = 0.0;
  float hit = 0.0;
  for (int i = 0; i < 74; i++){
    vec3 p = ro + rd * t;
    float d = map(p);
    if (d < 0.0015){ hit = 1.0; break; }
    if (t > 12.0) break;
    t += d * 0.86;               // slight under-relaxation: fewer artefacts
  }

  vec3 col = vec3(0.0);

  if (hit > 0.5){
    vec3 p = ro + rd * t;
    vec3 n = normal(p);
    vec3 v = -rd;

    float fres = pow(1.0 - max(dot(n, v), 0.0), 2.6);

    // two rim lights in the brand palette
    vec3 l1 = normalize(vec3(0.7, 0.8, 0.5));
    vec3 l2 = normalize(vec3(-0.8, -0.3, 0.4));
    float k1 = max(dot(n, l1), 0.0);
    float k2 = max(dot(n, l2), 0.0);

    vec3 acid  = vec3(0.64, 0.90, 0.21);   // #a3e635
    vec3 azure = vec3(0.20, 0.45, 0.95);

    // iridescent sheen driven by view angle + position
    vec3 irid = iridescence(fres * 0.9 + p.y * 0.12 + iTime * 0.02);

    // Chrome = reflection. Sample the environment along the mirror ray
    // and tint it with the thin-film ramp; almost no diffuse term.
    vec3 refl = reflect(rd, n);
    vec3 env  = envMap(refl);

    // fresnel drives how much environment we see (grazing = mirror)
    float F = mix(0.22, 1.0, fres);

    col  = env * irid * F * 2.1;
    col += env * 0.55;                       // base metal reflection
    col += acid  * pow(k1, 6.0) * 0.30;      // slight directional warmth
    col += azure * pow(k2, 6.0) * 0.20;
    col += irid * fres * 0.45;               // rainbow rim

    // fade into the background with depth
    col *= exp(-t * 0.055);
  }

  // ambient wash so the shapes sit in the page rather than on it
  float vig = 1.0 - 0.7 * length(uv * vec2(0.65, 1.0));
  col += vec3(0.02, 0.05, 0.07) * vig;

  // subtle grain to kill banding on the dark gradients
  float g = fract(sin(dot(gl_FragCoord.xy, vec2(12.9898, 78.233))) * 43758.5453);
  col += (g - 0.5) * 0.015;

  col = col / (0.72 + col);          // softened reinhard
  col = pow(col, vec3(0.78));        // lift midtones

  gl_FragColor = vec4(col, 1.0);
}
`;

function initHero() {
  const host = document.getElementById('fx');
  if (!host) return false;

  const cv = document.createElement('canvas');
  cv.setAttribute('aria-hidden', 'true');
  host.appendChild(cv);

  const gl = cv.getContext('webgl', {
    antialias: false, alpha: false, powerPreference: 'high-performance',
  }) || cv.getContext('experimental-webgl');
  if (!gl) { host.remove(); return false; }

  const compile = (type, src) => {
    const s = gl.createShader(type);
    gl.shaderSource(s, src);
    gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
      console.warn('shader:', gl.getShaderInfoLog(s));
      return null;
    }
    return s;
  };

  const vs = compile(gl.VERTEX_SHADER, VERT);
  const fs = compile(gl.FRAGMENT_SHADER, FRAG);
  if (!vs || !fs) { host.remove(); return false; }

  const prog = gl.createProgram();
  gl.attachShader(prog, vs);
  gl.attachShader(prog, fs);
  gl.linkProgram(prog);
  if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) { host.remove(); return false; }
  gl.useProgram(prog);

  // one oversized triangle covers the viewport with no seam
  const buf = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, buf);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
  const loc = gl.getAttribLocation(prog, 'p');
  gl.enableVertexAttribArray(loc);
  gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);

  const uRes = gl.getUniformLocation(prog, 'iRes');
  const uTime = gl.getUniformLocation(prog, 'iTime');
  const uPtr = gl.getUniformLocation(prog, 'iPointer');

  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const ptr = { x: 0, y: 0, tx: 0, ty: 0 };
  let raf = 0, running = false;
  // offset so the opening frame is an interesting pose, not the t=0 one
  let t0 = performance.now() - 9000;

  function resize() {
    // Raymarching is fill-rate bound: cap DPR so phones stay smooth.
    const dpr = Math.min(devicePixelRatio || 1, 1.5);
    const w = Math.round(host.clientWidth * dpr);
    const h = Math.round(host.clientHeight * dpr);
    if (cv.width === w && cv.height === h) return;
    cv.width = w; cv.height = h;
    gl.viewport(0, 0, w, h);
    gl.uniform2f(uRes, w, h);
  }

  function draw(now) {
    ptr.x += (ptr.tx - ptr.x) * 0.045;     // easing keeps the drift gentle
    ptr.y += (ptr.ty - ptr.y) * 0.045;
    gl.uniform1f(uTime, (now - t0) / 1000);
    gl.uniform2f(uPtr, ptr.x, ptr.y);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    if (running) raf = requestAnimationFrame(draw);
  }

  function start() {
    if (running || reduce) return;
    running = true;
    raf = requestAnimationFrame(draw);
  }
  function stop() {
    running = false;
    cancelAnimationFrame(raf);
  }

  resize();
  addEventListener('resize', () => { resize(); if (reduce) draw(performance.now()); },
    { passive: true });

  if (reduce) {
    draw(performance.now());               // one still frame, no loop
  } else {
    addEventListener('pointermove', (e) => {
      ptr.tx = (e.clientX / innerWidth) * 2 - 1;
      ptr.ty = -((e.clientY / innerHeight) * 2 - 1);
    }, { passive: true });

    new IntersectionObserver(([en]) => (en.isIntersecting ? start() : stop()),
      { threshold: 0 }).observe(host);

    document.addEventListener('visibilitychange',
      () => (document.hidden ? stop() : start()));

    start();
  }

  host.classList.add('on');
  return true;
}

window.initHero = initHero;
