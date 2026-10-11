// Netlify Function：房间数据 API（替代 PythonAnywhere 后端）
// 存储用 Netlify Blobs（免费、无需密钥、随站点自动注入上下文）
// 路由：netlify.toml 将 /api/* 重写到本函数
//
// GET  /api/state?room=R    -> {ok, room, version, people, data, ts}
// POST /api/state?room=R    -> 增量合并 {pids, people, data, del} / {reset:true} / {replace:true,...}
// GET  /api/hostinfo        -> {ok, lan:""}
const { getStore } = require('@netlify/blobs');

const STORE_NAME = 'free-time';
const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
};

function json(statusCode, obj) {
  return {
    statusCode,
    headers: { 'Content-Type': 'application/json; charset=utf-8', ...CORS },
    body: JSON.stringify(obj),
  };
}

function cleanRoom(s) {
  const v = String(s || '').trim().slice(0, 24).replace(/[^\w\u4e00-\u9fff-]/g, '');
  return v || 'default';
}
function cleanPid(p) {
  const v = String(p || '');
  return /^[A-Za-z0-9_-]{1,48}$/.test(v) ? v : null;
}
function cleanData(d) {
  const out = {};
  if (d && typeof d === 'object') {
    for (const k of Object.keys(d)) {
      if (d[k] && /^\d{1,2}_\d{1,2}$/.test(k)) out[k] = true;
    }
  }
  return out;
}
function cleanColor(c) {
  const v = String(c || '');
  return v.startsWith('#') && v.length <= 9 ? v : '#4066d5';
}

// 与 Python 版语义一致：按 person 并集合并，删除显式、最后执行
function merge(room, payload) {
  let people = Array.isArray(room.people) ? room.people : [];
  let data = room.data && typeof room.data === 'object' ? room.data : {};

  if (payload.reset) {
    people = [];
    data = {};
  } else if (payload.replace) {
    people = [];
    for (const p of payload.people || []) {
      const id = cleanPid(p && p.id);
      if (!id || !p.name) continue;
      people.push({ id, name: String(p.name).slice(0, 20), color: cleanColor(p.color) });
    }
    data = {};
    for (const p of people) {
      const dd = cleanData((payload.data || {})[p.id]);
      if (Object.keys(dd).length) data[p.id] = dd;
    }
  } else {
    const idx = new Map(people.map((p, i) => [p.id, i]));
    for (const rec of payload.people || []) {
      const id = cleanPid(rec && rec.id);
      if (!id) continue;
      if (idx.has(id)) {
        const p = people[idx.get(id)];
        if (rec.name) p.name = String(rec.name).slice(0, 20);
        if (typeof rec.color === 'string' && rec.color.startsWith('#')) p.color = rec.color.slice(0, 9);
      } else {
        people.push({ id, name: String(rec.name || '').slice(0, 20), color: cleanColor(rec.color) });
        idx.set(id, people.length - 1);
      }
    }
    const ids = new Set(people.map((p) => p.id));
    for (const raw of payload.pids || []) {
      const pid = cleanPid(raw);
      if (pid && ids.has(pid)) data[pid] = cleanData((payload.data || {})[pid]);
    }
    for (const raw of payload.del || []) {
      const pid = cleanPid(raw);
      if (!pid) continue;
      people = people.filter((p) => p.id !== pid);
      delete data[pid];
    }
  }

  room.people = people;
  room.data = data;
  room.version = (room.version || 0) + 1;
  room.ts = Math.floor(Date.now() / 1000);
  return room;
}

function openStore() {
  const opts = { name: STORE_NAME };
  const siteID = (process.env.BLOBS_SITE_ID || process.env.SITE_ID || process.env.NETLIFY_SITE_ID || '').trim();
  const token = (process.env.BLOBS_TOKEN || process.env.NETLIFY_BLOBS_TOKEN || '').trim();
  if (siteID) opts.siteID = siteID;
  if (token) opts.token = token;
  return getStore(opts);
}

exports.handler = async (event) => {
  const method = (event.httpMethod || 'GET').toUpperCase();
  if (method === 'OPTIONS') return { statusCode: 204, headers: CORS, body: '' };

  const path = (event.path || '') + ' ' + (event.rawUrl || '');
  if (/\/hostinfo\/?(?:[?#\s]|$)/.test(path)) return json(200, { ok: true, lan: '' });
  // 诊断（只回显变量名，不泄露值）：/api/state?debug=env
  if ((event.queryStringParameters || {}).debug) {
    return json(200, {
      ok: true,
      hasBlobsContext: !!process.env.NETLIFY_BLOBS_CONTEXT,
      hasSiteId: !!process.env.NETLIFY_SITE_ID,
      hasBlobsToken: !!process.env.NETLIFY_BLOBS_TOKEN,
      hasApiToken: !!process.env.NETLIFY_API_TOKEN,
      hasCustomSiteId: !!process.env.BLOBS_SITE_ID,
      hasCustomToken: !!process.env.BLOBS_TOKEN,
      siteIdUsed: (process.env.BLOBS_SITE_ID || process.env.SITE_ID || process.env.NETLIFY_SITE_ID || '').trim(),
      tokenLen: (process.env.BLOBS_TOKEN || process.env.NETLIFY_BLOBS_TOKEN || '').trim().length,
      node: process.version,
      envKeys: Object.keys(process.env).filter((k) => /BLOBS|NETLIFY|SITE|TOKEN/i.test(k)).sort(),
    });
  }

  const qs = event.queryStringParameters || {};
  const room = cleanRoom(qs.room);
  const key = 'room:' + room;
  const store = openStore();

  try {
    if (method === 'GET') {
      const cur = (await store.get(key, { type: 'json' })) || { people: [], data: {}, version: 0, ts: 0 };
      return json(200, {
        ok: true, room,
        version: cur.version || 0,
        people: cur.people || [],
        data: cur.data || {},
        ts: cur.ts || 0,
      });
    }
    if (method === 'POST') {
      let payload;
      try {
        const raw = event.isBase64Encoded ? Buffer.from(event.body || '', 'base64').toString('utf8') : (event.body || '{}');
        payload = JSON.parse(raw);
      } catch (e) {
        return json(400, { ok: false, error: 'bad_json' });
      }
      if (!payload || typeof payload !== 'object') return json(400, { ok: false, error: 'bad_json' });
      const cur = (await store.get(key, { type: 'json' })) || { people: [], data: {}, version: 0, ts: 0 };
      const next = merge(cur, payload);
      await store.setJSON(key, next);
      return json(200, { ok: true, room, version: next.version });
    }
    return json(405, { ok: false, error: 'method_not_allowed' });
  } catch (e) {
    return json(500, { ok: false, error: 'server_error', detail: String((e && e.message) || e).slice(0, 200) });
  }
};
