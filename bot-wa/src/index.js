/**
 * bot-wa Gateway Microservice
 * ===========================
 * Node.js + Express + Baileys microservice untuk mengirimkan notifikasi WhatsApp
 * dari sistem bot-oc dan bot-vb ke Merchant / Owner secara otomatis & terisolasi.
 */

const express = require('express');
const cors = require('cors');
const dotenv = require('dotenv');
const qrcode = require('qrcode-terminal');
const QRCodeGenerator = require('qrcode');
const pino = require('pino');
const path = require('path');
const fs = require('fs');
const https = require('https');

dotenv.config();

const {
  default: makeWASocket,
  useMultiFileAuthState,
  DisconnectReason,
  fetchLatestBaileysVersion
} = require('@whiskeysockets/baileys');

const app = express();
app.use(cors());
app.use(express.json());
app.use(express.static(path.join(__dirname, '../public')));

const PORT = process.env.PORT || 3002;
const WA_API_KEY = process.env.WA_API_KEY || 'foodmaster-wa-secret-2026-key';
const AUTH_DIR = process.env.WA_AUTH_DIR || path.join(__dirname, '../auth_info_baileys');

if (!fs.existsSync(AUTH_DIR)) {
  fs.mkdirSync(AUTH_DIR, { recursive: true });
}

// Global State
let sock = null;
let waStatus = 'INITIALIZING'; // INITIALIZING, QR_READY, CONNECTED, DISCONNECTED
let lastQr = null;
let lastQrImage = null;
let connectedUser = null;
let queue = [];
let isProcessingQueue = false;

// Logger
const logger = pino({ level: process.env.LOG_LEVEL || 'info' });

/**
 * Middleware Autentikasi API Key
 */
function authenticateApiKey(req, res, next) {
  const apiKey = req.headers['x-api-key'] || req.query.api_key;
  if (!apiKey || apiKey !== WA_API_KEY) {
    return res.status(401).json({
      success: false,
      error: 'Unauthorized. Header X-API-Key tidak valid.'
    });
  }
  next();
}

/**
 * Ekstrak Informasi Akun WhatsApp Terhubung
 */
function extractUserInfo() {
  if (!sock || !sock.user) return null;
  try {
    const userObj = sock.user;
    const rawId = userObj.id || '';
    const phoneDigits = rawId.split(':')[0].split('@')[0].replace(/[^0-9]/g, '');
    const formattedPhone = phoneDigits ? (phoneDigits.startsWith('62') ? '0' + phoneDigits.slice(2) : phoneDigits) : '';
    const rawName = userObj.name || userObj.notify || userObj.verifiedName || '';
    const name = (rawName && rawName !== 'Akun WhatsApp') ? rawName : null;

    return {
      name: name,
      phone: formattedPhone || phoneDigits || '-',
      phone_raw: phoneDigits,
      id: rawId
    };
  } catch (e) {
    return { name: null, phone: '-' };
  }
}

/**
 * Membersihkan seluruh isi folder autentikasi (tanpa menghapus folder mount point)
 */
function clearAuthDir() {
  if (fs.existsSync(AUTH_DIR)) {
    try {
      const files = fs.readdirSync(AUTH_DIR);
      for (const file of files) {
        const filePath = path.join(AUTH_DIR, file);
        try {
          fs.rmSync(filePath, { recursive: true, force: true });
        } catch (e) {
          logger.warn({ file: filePath, err: e.message }, 'Gagal menghapus file auth');
        }
      }
      logger.info('Folder autentikasi berhasil dibersihkan.');
    } catch (e) {
      logger.error({ err: e.message }, 'Gagal membaca folder auth untuk pembersihan');
    }
  }
}

/**
 * Inisialisasi Koneksi Baileys WhatsApp
 */
async function connectToWhatsApp() {
  try {
    const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
    const { version } = await fetchLatestBaileysVersion();

    sock = makeWASocket({
      version,
      auth: state,
      printQRInTerminal: false,
      logger: pino({ level: 'silent' }),
      browser: ['FoodMaster Bot WA', 'Chrome', '1.0.0']
    });

    sock.ev.on('creds.update', saveCreds);

    sock.ev.on('connection.update', (update) => {
      const { connection, lastDisconnect, qr } = update;

      if (qr) {
        lastQr = qr;
        waStatus = 'QR_READY';
        QRCodeGenerator.toDataURL(qr, { margin: 2, width: 260 }, (err, url) => {
          if (!err) lastQrImage = url;
        });
        console.log('\n================ WhatsApp Scan QR Code ================');
        qrcode.generate(qr, { small: true });
        console.log('Silakan scan QR Code di atas menggunakan aplikasi WhatsApp.');
        console.log('========================================================\n');
      }

      if (connection === 'close') {
        const statusCode = lastDisconnect?.error?.output?.statusCode;
        const shouldReconnect = statusCode !== DisconnectReason.loggedOut;

        if (shouldReconnect && (waStatus === 'QR_READY' || waStatus === 'CONNECTING' || waStatus === 'INITIALIZING')) {
          waStatus = 'CONNECTING';
        } else {
          waStatus = 'DISCONNECTED';
          connectedUser = null;
        }

        lastQr = null;
        lastQrImage = null;

        logger.warn({ statusCode, shouldReconnect }, 'Koneksi WhatsApp terputus.');

        if (shouldReconnect) {
          logger.info('Mencoba menyambungkan kembali dalam 5 detik...');
          setTimeout(connectToWhatsApp, 5000);
        } else {
          logger.warn('Session di-logout / expired. Membersihkan sesi auth dan menyiapkan QR code baru...');
          clearAuthDir();
          setTimeout(connectToWhatsApp, 2000);
        }
      } else if (connection === 'open') {
        waStatus = 'CONNECTED';
        lastQr = null;
        lastQrImage = null;
        connectedUser = extractUserInfo();
        logger.info({ connectedUser }, 'Koneksi WhatsApp BERHASIL terhubung 24/7!');
      }
    });
  } catch (err) {
    logger.error({ err }, 'Gagal menginisialisasi Baileys WhatsApp');
    setTimeout(connectToWhatsApp, 10000);
  }
}

function normalizePhoneNumber(rawPhone) {
  let cleaned = String(rawPhone || '').replace(/[^0-9]/g, '');
  if (!cleaned) return '';
  if (cleaned.startsWith('0')) {
    cleaned = '62' + cleaned.slice(1);
  } else if (cleaned.startsWith('8')) {
    cleaned = '62' + cleaned;
  }
  return cleaned;
}

// Anti-Spam / Deduplication Cache (TTL 5 Menit)
const DEDUP_TTL_MS = 5 * 60 * 1000;
const dedupCache = new Map();

function checkAndMarkDuplicate(dedupKey) {
  if (!dedupKey) return false;
  const now = Date.now();
  // Cleanup expired items
  for (const [k, ts] of dedupCache.entries()) {
    if (now - ts > DEDUP_TTL_MS) dedupCache.delete(k);
  }
  if (dedupCache.has(dedupKey)) {
    return true;
  }
  dedupCache.set(dedupKey, now);
  return false;
}

/**
 * Worker Penangan Antrean Pesan (Anti-Ban & Anti-Spam Rate Limiting)
 */
async function processQueue() {
  if (isProcessingQueue || queue.length === 0) return;
  isProcessingQueue = true;

  while (queue.length > 0) {
    const task = queue.shift();
    try {
      if (waStatus !== 'CONNECTED' || !sock) {
        throw new Error('Koneksi WhatsApp sedang tidak terhubung.');
      }
      const cleaned = normalizePhoneNumber(task.phone);
      if (!cleaned) {
        throw new Error(`Nomor telepon tidak valid: ${task.phone}`);
      }
      const formattedJid = cleaned + '@s.whatsapp.net';

      // 1. Simulasi status mengetik (Human Emulation)
      try {
        await sock.sendPresenceUpdate('composing', formattedJid);
        const typingDelay = Math.floor(800 + Math.random() * 800); // 800ms - 1600ms
        await new Promise((r) => setTimeout(r, typingDelay));
        await sock.sendPresenceUpdate('paused', formattedJid);
      } catch (presErr) {
        // Abaikan error presence jika network lambat
      }

      // 2. Kirim pesan aktual
      await sock.sendMessage(formattedJid, { text: task.message });
      logger.info({ phone: task.phone, jid: formattedJid }, 'Pesan WA berhasil terkirim');
      if (task.resolve) task.resolve({ success: true, phone: task.phone, jid: formattedJid });
    } catch (err) {
      logger.error({ err: err.message, phone: task.phone }, 'Gagal mengirim pesan WA');
      if (task.reject) task.reject(err);
    }

    // 3. Jeda aman acak (Jitter Pacing: 2.5s - 4.5s) antar pesan untuk perlindungan anti-ban
    const safeJitterDelay = Math.floor(2500 + Math.random() * 2000);
    await new Promise((r) => setTimeout(r, safeJitterDelay));
  }

  isProcessingQueue = false;
}

function enqueueMessage(phoneInput, message, dedupKey = null) {
  if (!phoneInput) return Promise.resolve({ success: false, error: 'Nomor kosong' });
  const phoneList = String(phoneInput)
    .split(/[,;\n]+/)
    .map(p => p.trim())
    .filter(Boolean);

  if (phoneList.length === 0) {
    return Promise.resolve({ success: false, error: 'Nomor kosong' });
  }

  // Cek deduplikasi jika diberikan dedupKey
  if (dedupKey && checkAndMarkDuplicate(dedupKey)) {
    logger.warn({ dedupKey, phoneInput }, '[ANTI-SPAM] Pesan duplikat dicegah (cooldown 5 menit aktif)');
    return Promise.resolve({ success: true, deduplicated: true, message: 'Pesan duplikat dicegah oleh proteksi Anti-Spam.' });
  }

  // Batasi kapasitas antrean maksimal 100 pesan
  if (queue.length >= 100) {
    logger.warn('Kapasitas antrean pesan WA penuh (100). Pesan baru diabaikan untuk proteksi.');
    return Promise.resolve({ success: false, error: 'Antrean pesan WA penuh.' });
  }

  const promises = phoneList.map(phone => {
    return new Promise((resolve, reject) => {
      // Hindari duplikasi task identik di antrean yang belum terproses
      const isAlreadyInQueue = queue.some(t => t.phone === phone && t.message === message);
      if (isAlreadyInQueue) {
        logger.info({ phone }, '[QUEUE DEDUP] Pesan identik sudah ada di antrean.');
        resolve({ success: true, deduplicated: true });
        return;
      }
      queue.push({ phone, message, resolve, reject });
    });
  });

  processQueue();
  return Promise.all(promises);
}

/**
 * Format Teks Notifikasi WhatsApp Berdasarkan Event
 */
function buildNotificationText(body) {
  const { event_type, platform, merchant_name, outlet_name, store_id, action, live_status, error_type, detail, timestamp } = body;
  const timeStr = timestamp || new Date().toLocaleString('id-ID', { timeZone: 'Asia/Jakarta' });

  const cleanStoreId = String(store_id || '').trim();
  const shopeeLink = cleanStoreId && cleanStoreId !== '-' && cleanStoreId !== 'SYSTEM'
    ? `https://shopee.co.id/universal-link/now-food/shop/${cleanStoreId}`
    : '-';

  if (event_type === 'ACTION_OPEN') {
    return (
      `🟢 *OUTLET BERHASIL DIBUKA BOT*\n\n` +
      `Nama Outlet: *${outlet_name}*\n` +
      `Store ID: ${cleanStoreId || '-'}\n` +
      `Lihat di ShopeeFood:\n${shopeeLink}\n\n` +
      `_FoodMaster Bot Team_\n` +
      `_WA CS: wa.me/6285183151531_`
    );
  }

  if (event_type === 'ACTION_CLOSE' || event_type === 'ACTION_PAUSE') {
    return (
      `🔴 *OUTLET BERHASIL DITUTUP BOT*\n\n` +
      `Nama Outlet: *${outlet_name}*\n` +
      `Store ID: ${cleanStoreId || '-'}\n` +
      `Lihat di ShopeeFood:\n${shopeeLink}\n\n` +
      `_FoodMaster Bot Team_\n` +
      `_WA CS: wa.me/6285183151531_`
    );
  }

  if (event_type === 'ACTION_SKIPPED') {
    return (
      `⚠️ *OUTLET DI-SKIP (JADWAL KHUSUS)*\n\n` +
      `Nama Outlet: *${outlet_name}*\n` +
      `Store ID: ${cleanStoreId || '-'}\n` +
      `Status Shopee: *${live_status || 'UNKNOWN'}*\n` +
      `Catatan: Toko memiliki Jadwal Khusus / Libur.\n\n` +
      `_FoodMaster Bot Team_\n` +
      `_WA CS: wa.me/6285183151531_`
    );
  }

  if (event_type === 'BOT_ERROR') {
    return (
      `❌ *PERINGATAN EROR BOT PATROLI*\n\n` +
      `Nama Outlet: *${outlet_name}*\n` +
      `Store ID: ${cleanStoreId || '-'}\n` +
      `Tipe Error: ${error_type || 'Unknown Exception'}\n` +
      `Detail: ${detail || 'Gagal memverifikasi status'}\n\n` +
      `_FoodMaster Bot Team_\n` +
      `_WA CS: wa.me/6285183151531_`
    );
  }

  // Fallback Pesan Generik
  return (
    `ℹ️ *NOTIFIKASI FOODMASTER*\n\n` +
    `Nama Outlet: *${outlet_name}*\n` +
    `Store ID: ${cleanStoreId || '-'}\n` +
    `Informasi: ${detail || action || 'Pesan dari sistem'}\n\n` +
    `_FoodMaster Bot Team_\n` +
    `_WA CS: wa.me/6285183151531_`
  );
}

// Agency Google Sheet URL
const GOOGLE_SHEETS_CSV_URL = process.env.GOOGLE_SHEETS_CSV_URL || 
  'https://docs.google.com/spreadsheets/d/e/2PACX-1vSsAq8JmDfGI8KY7aSCRpzC2EaQARkK1OvhWrll7g3qlxFMIcwtDpAF-Wxf4aQnGET4eCmncjdEgre5/pub?gid=890126027&single=true&output=csv';

let cachedOwnersData = null;
let lastFetchTimestamp = 0;

// Helper Parse CSV
function parseCSV(text) {
  const lines = text.split(/\r?\n/).filter(line => line.trim().length > 0);
  if (lines.length === 0) return [];
  
  function parseLine(line) {
    const values = [];
    let current = '';
    let insideQuotes = false;
    for (let i = 0; i < line.length; i++) {
      const char = line[i];
      if (char === '"') {
        if (insideQuotes && line[i + 1] === '"') {
          current += '"';
          i++;
        } else {
          insideQuotes = !insideQuotes;
        }
      } else if (char === ',' && !insideQuotes) {
        values.push(current.trim());
        current = '';
      } else {
        current += char;
      }
    }
    values.push(current.trim());
    return values;
  }

  const rawHeaders = parseLine(lines[0]);
  const headers = rawHeaders.map(h => h.trim().toLowerCase());

  function findCol(patterns, exclude = []) {
    for (let i = 0; i < headers.length; i++) {
      const h = headers[i];
      if (exclude.some(ex => h.includes(ex))) continue;
      if (patterns.some(p => h.includes(p))) return i;
    }
    return -1;
  }

  const colOwner = findCol(['nama pemilik', 'pemilik'], ['wa', 'hp', 'no']);
  const colPhone = findCol(['nomor hp', 'wa', 'whatsapp', 'hp', 'telepon']);
  const colStatus = findCol(['status'], ['langganan', 'subscription']);
  const colPaket = findCol(['paket', 'package']);
  const colMulai = findCol(['mulai', 'start']);
  const colBerakhir = findCol(['berakhir', 'expired', 'end']);
  const colPortal = findCol(['nama portal', 'portal', 'merchant']);
  const colStoreId = findCol(['store id', 'store_id', 'store']);
  const colNamaListing = findCol(['nama listing', 'nama panjang', 'listing', 'outlet'], ['portal']);

  const rows = [];
  for (let i = 1; i < lines.length; i++) {
    const vals = parseLine(lines[i]);
    if (!vals || vals.length === 0) continue;
    const getVal = (idx) => (idx >= 0 && idx < vals.length ? vals[idx].trim() : '');

    const ownerName = getVal(colOwner >= 0 ? colOwner : 0);
    if (!ownerName) continue;

    rows.push({
      owner: ownerName,
      phone: getVal(colPhone >= 0 ? colPhone : 1),
      status: getVal(colStatus >= 0 ? colStatus : 2) || 'Aktif',
      package: getVal(colPaket >= 0 ? colPaket : 3) || '-',
      start_date: getVal(colMulai >= 0 ? colMulai : 4) || '-',
      end_date: getVal(colBerakhir >= 0 ? colBerakhir : 5) || '-',
      portal: getVal(colPortal >= 0 ? colPortal : 8),
      store_id: getVal(colStoreId >= 0 ? colStoreId : 9),
      outlet_name: getVal(colNamaListing >= 0 ? colNamaListing : 10) || getVal(colStoreId >= 0 ? colStoreId : 9)
    });
  }
  return rows;
}

function downloadCsvText(targetUrl, maxRedirects = 5) {
  return new Promise((resolve, reject) => {
    if (maxRedirects < 0) return reject(new Error('Too many redirects'));
    const req = https.get(targetUrl, { family: 4, timeout: 15000 }, (res) => {
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        return downloadCsvText(res.headers.location, maxRedirects - 1).then(resolve).catch(reject);
      }
      if (res.statusCode !== 200) {
        return reject(new Error(`HTTP ${res.statusCode}: ${res.statusMessage}`));
      }
      let data = '';
      res.on('data', chunk => { data += chunk; });
      res.on('end', () => resolve(data));
    });
    req.on('error', reject);
    req.on('timeout', () => {
      req.destroy();
      reject(new Error('Request timeout fetching Google Sheet CSV'));
    });
  });
}

async function fetchAgencyOwnersFromSheet() {
  try {
    const csvText = await downloadCsvText(GOOGLE_SHEETS_CSV_URL);
    const rows = parseCSV(csvText);

    const ownersMap = {};
    for (const r of rows) {
      const owner = r.owner;
      if (!owner) continue;

      if (!ownersMap[owner]) {
        ownersMap[owner] = {
          owner: owner,
          phones: [],
          package: r.package,
          subscription_status: r.status,
          start_date: r.start_date,
          end_date: r.end_date,
          outlets: []
        };
      }

      if (r.phone && r.phone !== '-' && !ownersMap[owner].phones.includes(r.phone)) {
        ownersMap[owner].phones.push(r.phone);
      }

      if (r.store_id || r.outlet_name) {
        ownersMap[owner].outlets.push({
          store_id: r.store_id,
          outlet_name: r.outlet_name || r.store_id,
          portal: r.portal,
          status: r.status,
          package: r.package
        });
      }
    }

    const ownersList = Object.values(ownersMap).sort((a, b) => a.owner.localeCompare(b.owner));
    cachedOwnersData = ownersList;
    lastFetchTimestamp = Date.now();
    logger.info({ totalOwners: ownersList.length, totalOutlets: rows.length }, 'Data Owner Agency Google Sheet berhasil di-fetch.');
    return ownersList;
  } catch (err) {
    logger.error({ err: err.message }, 'Gagal fetch Agency Google Sheet, mencoba fallback cache/file');
    return cachedOwnersData || [];
  }
}

async function getOwnersData(forceRefresh = false) {
  if (!forceRefresh && cachedOwnersData && (Date.now() - lastFetchTimestamp < 300000)) {
    return cachedOwnersData;
  }
  return await fetchAgencyOwnersFromSheet();
}

// Health check route
app.get('/health', (req, res) => {
  res.json({
    status: 'ok',
    service: 'bot-wa-gateway',
    timestamp: new Date().toISOString()
  });
});

// Wa status route
app.get('/api/v1/status', (req, res) => {
  const userInfo = connectedUser || extractUserInfo();
  res.json({
    success: true,
    wa_status: waStatus,
    qr_code_raw: lastQr || null,
    qr_code_image: lastQrImage || null,
    user: userInfo || null,
    queue_length: queue.length
  });
});

// Owners & Configuration route (Grouped by Unique Owner from Agency Sheet)
app.get('/api/v1/owners', async (req, res) => {
  try {
    const forceRefresh = req.query.refresh === 'true' || req.query.sync === '1';
    const owners = await getOwnersData(forceRefresh);
    res.json({
      success: true,
      total_owners: owners.length,
      total_outlets: owners.reduce((acc, o) => acc + (o.outlets ? o.outlets.length : 0), 0),
      data: owners
    });
  } catch (e) {
    res.status(500).json({ success: false, error: e.message });
  }
});

// Sync Agency Sheet route
app.post('/api/v1/sync-sheet', async (req, res) => {
  try {
    const owners = await getOwnersData(true);
    res.json({
      success: true,
      message: 'Data Google Sheet Agency berhasil disinkronkan.',
      total_owners: owners.length,
      total_outlets: owners.reduce((acc, o) => acc + (o.outlets ? o.outlets.length : 0), 0),
      data: owners
    });
  } catch (e) {
    res.status(500).json({ success: false, error: e.message });
  }
});

// Logout & Reset Session Route
app.post('/api/v1/logout', authenticateApiKey, async (req, res) => {
  try {
    if (sock) {
      try {
        await sock.logout();
      } catch (e) {}
      try {
        sock.end();
      } catch (e) {}
      sock = null;
    }
    waStatus = 'DISCONNECTED';
    lastQr = null;
    lastQrImage = null;
    connectedUser = null;

    clearAuthDir();

    res.json({
      success: true,
      message: 'Sesi WhatsApp berhasil di-logout dan siap scan QR baru.'
    });

    setTimeout(() => {
      connectToWhatsApp();
    }, 1500);
  } catch (err) {
    logger.error({ err }, 'Gagal melakukan logout WA');
    res.status(500).json({
      success: false,
      error: err.message
    });
  }
});

// Direct Send Message Route
app.post('/api/v1/send-message', authenticateApiKey, async (req, res) => {
  const { phone, message, dedup_key } = req.body;

  if (!phone || !message) {
    return res.status(400).json({
      success: false,
      error: 'Parameter `phone` dan `message` wajib diisi.'
    });
  }

  try {
    const key = dedup_key || `${phone}:${message.slice(0, 32)}`;
    const result = await enqueueMessage(phone, message, key);
    res.json({
      success: true,
      message: 'Pesan berhasil diproses ke dalam antrean WA.',
      data: result
    });
  } catch (err) {
    res.status(500).json({
      success: false,
      error: err.message
    });
  }
});

// Webhook Bot Action Notification Route (Used by bot-oc and bot-vb)
app.post('/api/v1/webhook/bot-action', authenticateApiKey, async (req, res) => {
  const { phone, merchant_name, outlet_name, store_id, event_type } = req.body;

  if (!phone || !merchant_name || !outlet_name) {
    return res.status(400).json({
      success: false,
      error: 'Payload webhook tidak lengkap (`phone`, `merchant_name`, `outlet_name` wajib).'
    });
  }

  const dedupKey = `BOT:${phone}:${event_type || 'ACT'}:${store_id || outlet_name}`;
  const messageText = buildNotificationText(req.body);

  try {
    const result = await enqueueMessage(phone, messageText, dedupKey);
    res.json({
      success: true,
      message: 'Webhook diterima dan notifikasi WA diproses.',
      event_type: event_type || 'GENERAL',
      deduplicated: Boolean(result && result.deduplicated)
    });
  } catch (err) {
    res.status(500).json({
      success: false,
      error: err.message
    });
  }
});

// Start Server
app.listen(PORT, () => {
  logger.info(`Server bot-wa Gateway berjalan di port ${PORT}`);
  connectToWhatsApp();
});
