# Guide Masuk Business Hours dan Inspect Fetch/XHR

1. Masuk ke tab business-hours dengan URL:

```text
https://partner.shopee.co.id/settings/shopee-food/business-hours-settings/business-hours?storeId={store_id}
```

2. Pastikan session login Shopee Partner masih aktif dan outlet target memang terbuka di halaman itu.
3. Buka DevTools -> `Network` -> filter `Fetch/XHR`.
4. Setelah halaman business-hours termuat, request read seperti `/api/seller/store` dan `/api/seller/store/regular-hours` akan muncul.
5. Jika menjalankan aksi buka atau pause, request `action/open` dan `action/pause` juga akan muncul pada panel yang sama.
6. Header, payload, dan response contoh sudah disimpan di folder `DOCS/`.
7. Penjelasan teknis lengkapnya ada di [fetch-xhr-scraping-eksekusi-api.md](./fetch-xhr-scraping-eksekusi-api.md).
