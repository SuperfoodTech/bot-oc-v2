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
const WA_API_KEY = process.env.WA_API_KEY || 'change-this-wa-secret-key';
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
          logger.error('Session di-logout dari HP. Hapus folder auth dan restart service untuk scan ulang.');
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

/**
 * Worker Penangan Antrean Pesan (Anti-Ban Rate Limiting)
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
      const formattedPhone = task.phone.replace(/[^0-9]/g, '') + '@s.whatsapp.net';
      await sock.sendMessage(formattedPhone, { text: task.message });
      if (task.resolve) task.resolve({ success: true, phone: task.phone });
    } catch (err) {
      logger.error({ err: err.message, phone: task.phone }, 'Gagal mengirim pesan WA');
      if (task.reject) task.reject(err);
    }
    // Delay 1.5 detik antar kiriman pesan untuk mencegah penangguhan nomor
    await new Promise((r) => setTimeout(r, 1500));
  }

  isProcessingQueue = false;
}

function enqueueMessage(phone, message) {
  return new Promise((resolve, reject) => {
    queue.push({ phone, message, resolve, reject });
    processQueue();
  });
}

/**
 * Format Teks Notifikasi WhatsApp Berdasarkan Event
 */
function buildNotificationText(body) {
  const { event_type, platform, merchant_name, outlet_name, store_id, action, live_status, error_type, detail, timestamp } = body;
  const timeStr = timestamp || new Date().toLocaleString('id-ID', { timeZone: 'Asia/Jakarta' });
  const platformName = platform || 'Shopee';

  if (event_type === 'ACTION_OPEN') {
    return (
      `🟢 *[OUTLET DIBUKA]*\n\n` +
      `Halo *${merchant_name}*,\n` +
      `Outlet *${outlet_name}* (${platformName} - ID: ${store_id || '-'}) telah *BERHASIL DIBUKA* oleh bot patroli.\n\n` +
      `Waktu: ${timeStr}\n` +
      `Status Live: OPEN\n\n` +
      `_Pesan otomatis dari Bot FoodMaster System._`
    );
  }

  if (event_type === 'ACTION_CLOSE' || event_type === 'ACTION_PAUSE') {
    return (
      `🟡 *[OUTLET DITUTUP / PAUSE]*\n\n` +
      `Halo *${merchant_name}*,\n` +
      `Outlet *${outlet_name}* (${platformName} - ID: ${store_id || '-'}) telah *BERHASIL DITUTUP* oleh bot patroli.\n\n` +
      `Waktu: ${timeStr}\n` +
      `Status Live: PAUSE / CLOSED\n\n` +
      `_Pesan otomatis dari Bot FoodMaster System._`
    );
  }

  if (event_type === 'ACTION_SKIPPED') {
    return (
      `⚠️ *[OUTLET DI-SKIP (JADWAL KHUSUS)]*\n\n` +
      `Halo *${merchant_name}*,\n` +
      `Outlet *${outlet_name}* (${platformName}) di-SKIP dari paksa status.\n\n` +
      `Status Live Shopee: *${live_status || 'UNKNOWN'}*\n` +
      `Ekspektasi Aksi: *${action || '-'}*\n` +
      `Catatan: Toko memiliki Jadwal Khusus / Libur di Shopee.\n` +
      `Waktu: ${timeStr}\n\n` +
      `_Pesan otomatis dari Bot FoodMaster System._`
    );
  }

  if (event_type === 'BOT_ERROR') {
    return (
      `❌ *[PERINGATAN EROR BOT]*\n\n` +
      `Perhatian Admin/Merchant *${merchant_name}*,\n` +
      `Terjadi kendala patroli pada outlet *${outlet_name}* (${platformName}).\n\n` +
      `Tipe Error: ${error_type || 'Unknown Exception'}\n` +
      `Detail: ${detail || 'Gagal melakukan konfirmasi status'}\n` +
      `Waktu: ${timeStr}\n\n` +
      `_Pesan otomatis dari Bot FoodMaster System._`
    );
  }

  // Fallback Pesan Generik
  return (
    `ℹ️ *[NOTIFIKASI FOODMASTER]*\n\n` +
    `Merchant: *${merchant_name}*\n` +
    `Outlet: *${outlet_name}*\n` +
    `Informasi: ${detail || action || 'Pesan dari sistem'}\n` +
    `Waktu: ${timeStr}`
  );
}

// ================= ROUTE API =================

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
    if (fs.existsSync(AUTH_DIR)) {
      fs.rmSync(AUTH_DIR, { recursive: true, force: true });
    }
    fs.mkdirSync(AUTH_DIR, { recursive: true });
    res.json({
      success: true,
      message: 'Sesi WhatsApp berhasil di-logout dan folder autentikasi dibersihkan.'
    });
    setTimeout(connectToWhatsApp, 2000);
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
  const { phone, message } = req.body;

  if (!phone || !message) {
    return res.status(400).json({
      success: false,
      error: 'Parameter `phone` dan `message` wajib diisi.'
    });
  }

  try {
    const result = await enqueueMessage(phone, message);
    res.json({
      success: true,
      message: 'Pesan berhasil dimasukkan ke dalam antrean WA.',
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
  const { phone, merchant_name, outlet_name } = req.body;

  if (!phone || !merchant_name || !outlet_name) {
    return res.status(400).json({
      success: false,
      error: 'Payload webhook tidak lengkap (`phone`, `merchant_name`, `outlet_name` wajib).'
    });
  }

  const messageText = buildNotificationText(req.body);

  try {
    enqueueMessage(phone, messageText);
    res.json({
      success: true,
      message: 'Webhook diterima dan notifikasi WA dijadwalkan.',
      event_type: req.body.event_type || 'GENERAL'
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
