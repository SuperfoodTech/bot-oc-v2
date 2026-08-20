/**
 * FoodMaster Google Sheets write-back endpoint.
 *
 * Supported operation:
 *   POST {"action":"deactivate","store_id":"21708900","token":"..."}
 *
 * Configure these Script Properties before deploying:
 *   SPREADSHEET_ID = 10osh4rI4q_mv6fBe9NurXRztRrGa85L01Bwned6m0Qs
 *   SHEET_GID      = 0
 *   WEBHOOK_TOKEN  = a-long-random-secret
 */

function doGet() {
  return jsonResponse({
    success: true,
    service: 'foodmaster-google-sheets-writeback',
  });
}

function doPost(event) {
  var lock = LockService.getScriptLock();

  try {
    var payload = parsePayload(event);
    requireToken(payload.token);

    if (payload.action !== 'deactivate') {
      throw new Error('Unsupported action.');
    }

    var storeId = String(payload.store_id || '').trim();
    if (!storeId) {
      throw new Error('store_id is required.');
    }

    lock.waitLock(20000);
    var result = deactivateStore(storeId);
    return jsonResponse({
      success: true,
      action: 'deactivate',
      store_id: storeId,
      status: result.status,
      row: result.row,
    });
  } catch (error) {
    return jsonResponse({
      success: false,
      error: error && error.message ? error.message : String(error),
    });
  } finally {
    try {
      lock.releaseLock();
    } catch (ignored) {
      // The lock may not have been acquired when validation failed.
    }
  }
}

function deactivateStore(storeId) {
  var properties = PropertiesService.getScriptProperties();
  var spreadsheetId = properties.getProperty('SPREADSHEET_ID');
  var sheetGid = Number(properties.getProperty('SHEET_GID') || '0');

  if (!spreadsheetId) {
    throw new Error('SPREADSHEET_ID is not configured.');
  }

  var spreadsheet = SpreadsheetApp.openById(spreadsheetId);
  var sheet = spreadsheet.getSheets().filter(function (candidate) {
    return candidate.getSheetId() === sheetGid;
  })[0];

  if (!sheet) {
    throw new Error('Worksheet with configured SHEET_GID was not found.');
  }

  var values = sheet.getDataRange().getDisplayValues();
  if (!values.length) {
    throw new Error('Worksheet is empty.');
  }

  var headers = values[0].map(normalizeHeader);
  var storeIdColumn = headers.indexOf('store id');
  var statusColumn = headers.indexOf('status');

  if (storeIdColumn < 0 || statusColumn < 0) {
    throw new Error('Required headers "Store ID" and "Status" were not found.');
  }

  var matchedRow = -1;
  for (var index = 1; index < values.length; index += 1) {
    var currentStoreId = String(values[index][storeIdColumn] || '').trim();
    if (currentStoreId !== storeId) {
      continue;
    }
    if (matchedRow !== -1) {
      throw new Error('Duplicate Store ID found in worksheet: ' + storeId);
    }
    matchedRow = index + 1; // Spreadsheet rows are 1-based, including header.
  }

  if (matchedRow === -1) {
    throw new Error('Store ID was not found: ' + storeId);
  }

  var currentStatus = String(values[matchedRow - 1][statusColumn] || '').trim();
  if (currentStatus !== 'Nonaktif') {
    sheet.getRange(matchedRow, statusColumn + 1).setValue('Nonaktif');
    SpreadsheetApp.flush();
  }

  return { row: matchedRow, status: 'Nonaktif' };
}

function parsePayload(event) {
  if (!event || !event.postData || !event.postData.contents) {
    throw new Error('JSON request body is required.');
  }

  try {
    return JSON.parse(event.postData.contents);
  } catch (error) {
    throw new Error('Invalid JSON request body.');
  }
}

function requireToken(token) {
  var expected = PropertiesService.getScriptProperties().getProperty('WEBHOOK_TOKEN');
  if (!expected) {
    throw new Error('WEBHOOK_TOKEN is not configured.');
  }
  if (!token || String(token) !== expected) {
    throw new Error('Unauthorized.');
  }
}

function normalizeHeader(value) {
  return String(value || '').trim().toLowerCase();
}

function jsonResponse(body) {
  return ContentService
    .createTextOutput(JSON.stringify(body))
    .setMimeType(ContentService.MimeType.JSON);
}
