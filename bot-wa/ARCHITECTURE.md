# Arsitektur Microservice `bot-wa` (WhatsApp Gateway)

Dokumen ini mendeskripsikan arsitektur sistem, topologi jaringan terpisah, manajemen sesi, dan alur integrasi webhook antara sistem **FoodMaster Bot OC / Bot VB** dan microservice **bot-wa Gateway**.

---

## 1. Topologi Jaringan & Arsitektur Terpisah

Service `bot-wa` didesain untuk berjalan sebagai **Microservice Terpisah** di VPS / Server lain yang terisolasi dari server bot patroli (`bot-oc` dan `bot-vb`).

```text
┌────────────────────────────────────────────────────────┐
│               SERVER 1: BOT OC & BOT VB                │
│ ┌──────────────────────┐    ┌────────────────────────┐ │
│ │ Container: fm-bot    │    │ Container: fm-bot-vb   │ │
│ │ (Python / Selenium)  │    │ (Python / Selenium)    │ │
│ └──────────┬───────────┘    └───────────┬────────────┘ │
└────────────┼────────────────────────────┼──────────────┘
             │ HTTP POST Webhook (Async)  │ (X-API-Key)
             └──────────────┬─────────────┘
                            ▼
┌────────────────────────────────────────────────────────┐
│               SERVER 2: WHATSAPP GATEWAY               │
│ ┌────────────────────────────────────────────────────┐ │
│ │ Container: fm-wa-gateway (Node.js + Baileys)       │ │
│ │                                                    │ │
│ │  ┌──────────────┐   ┌────────────┐   ┌──────────┐  │ │
│ │  │ Express API  ├──►│ Message    ├──►│ Baileys  │  │ │
│ │  │ Webhook      │   │ Queue      │   │ WebSocket│  │ │
│ │  └──────────────┘   └────────────┘   └────┬─────┘  │ │
│ └───────────────────────────────────────────┼────────┘ │
└─────────────────────────────────────────────┼──────────┘
                                              ▼
                             ┌──────────────────────────────────┐
                             │ WhatsApp Server / Cloud Platform │
                             └────────────────┬─────────────────┘
                                              ▼
                             ┌──────────────────────────────────┐
                             │ HP Merchant / Owner WhatsApp App │
                             └──────────────────────────────────┘
```

### Keuntungan Arsitektur Terpisah:
1. **Keandalan Session WA**: Sesi login WhatsApp (`auth_info_baileys`) tersimpan di volume terisolasi di Server 2, sehingga tidak pernah terputus meskipun Server 1 me-restart atau di-deploy ulang.
2. **Isolasi Resource**: Headless Chrome Selenium di Server 1 tidak akan membebani memory/CPU dari Node.js WhatsApp Gateway di Server 2.
3. **Multi-Tenant / Shared Gateway**: Server 2 dapat menerima notifikasi dari berbagai server bot sekaligus melalui endpoint REST Webhook.

---

## 2. Diagram Alur Kerja Notifikasi (Sequence Diagram)

```mermaid
sequenceDiagram
    autonumber
    participant Bot as Bot Patroli Engine (Python)
    participant Webhook as WA Gateway Express API
    participant Queue as Anti-Spam Queue Worker
    participant Baileys as Baileys WS Client
    participant WA as Merchant WhatsApp

    Note over Bot: Bot berhasil ubah status outlet (OPEN/CLOSE/SKIPPED)
    Bot->>Webhook: POST /api/v1/webhook/bot-action (Header: X-API-Key, Payload JSON)
    activate Webhook
    Webhook->>Webhook: Validasi X-API-Key & Schema Payload
    Webhook-->>Bot: 200 OK ({"success": true, "message": "Scheduled"})
    deactivate Bot

    Webhook->>Queue: Enqueue Message Task (Phone + Formatted Text)
    activate Queue
    Queue->>Queue: Delay 1.5 detik (Rate-limiting anti-ban)
    Queue->>Baileys: sendMessage(formattedPhone, text)
    activate Baileys
    Baileys->>WA: Kirim Pesan Terenkripsi (End-to-End)
    Baileys-->>Queue: Sent Status (ACK)
    deactivate Baileys
    deactivate Queue
```

---

## 3. Manajemen Session & Reconnection Policy

1. **Multi-File Auth State**:
   - Sesi disimulasikan menggunakan `useMultiFileAuthState` yang menyimpan credential login di direktori `./auth_info_baileys`.
   - Data sesi dipasang menggunakan Docker Volume (`wa_session_data`) agar persisten meskipun container di-restart.

2. **Auto-Reconnect Policy**:
   - Jika koneksi terputus karena masalah jaringan (*DisconnectReason.connectionClosed* / *timedOut*), service akan mencoba *reconnect* otomatis setiap 5 detik.
   - Jika sesi di-logout dari aplikasi WhatsApp di HP (*DisconnectReason.loggedOut*), service akan mengubah status menjadi `DISCONNECTED`. Admin perlu menghapus folder auth dan melakukan scan QR ulang.

---

## 4. Strategi Anti-Ban & Rate Limiting

WhatsApp memiliki sistem deteksi spam otomatis untuk nomor yang mengirim banyak pesan dalam waktu bersamaan. Untuk mencegah pemblokiran nomor:

- **Message Queue Worker**: Semua notifikasi dimasukkan ke dalam antrean internal (`queue`).
- **Throttling Delay**: Antrean diproses secara sekuensial dengan jeda minimal **1.5 detik** antar pengiriman pesan.
- **Deduplikasi Notifikasi**: Sistem bot-oc/bot-vb meng-cache notifikasi serupa dalam kurun waktu 5 menit agar tidak mengirim pesan redundan ke merchant yang sama.
