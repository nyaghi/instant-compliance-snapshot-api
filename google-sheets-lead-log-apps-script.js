/*
CharityClarity master lead log Google Apps Script

Use this script in a Google Sheet to receive CharityClarity lead rows from the
Render backend. Deploy as a Web App and set the Web App URL in Render as:

CE_LEAD_LOG_WEBHOOK_URL=<your Apps Script web app URL>
CE_LEAD_LOG_WEBHOOK_SECRET=<same secret you put below>

The sheet becomes the durable master log. The backend still keeps its local CSV
as a fallback/download, but this sheet is the one to bookmark.
*/

const CHARITY_CLARITY_LEAD_LOG_SECRET = "CHANGE_ME_TO_A_LONG_PRIVATE_SECRET";
const SPREADSHEET_ID = "1Gr7VVbiB1SiPj8_l2w8d9orpvY300A6OqcdVU78DTV4";
const SHEET_NAME = "Lead Log";
const HEADERS = [
  "checked_at",
  "email",
  "domain",
  "organization_name",
  "ein",
  "state",
  "status",
  "comments",
  "lookup_seconds",
  "app_version",
  "source_url",
  "received_at"
];

function doPost(e) {
  try {
    const payload = JSON.parse(e.postData.contents || "{}");
    if (CHARITY_CLARITY_LEAD_LOG_SECRET && payload.secret !== CHARITY_CLARITY_LEAD_LOG_SECRET) {
      return jsonResponse({ ok: false, error: "Unauthorized" }, 403);
    }

    const rows = Array.isArray(payload.rows) ? payload.rows : [];
    if (!rows.length) {
      return jsonResponse({ ok: true, appended: 0 });
    }

    const sheet = getLeadSheet_();
    const now = new Date();
    const values = rows.map((row) => [
      row.checked_at || "",
      row.email || "",
      row.domain || "",
      row.organization_name || "",
      row.ein || "",
      row.state || "",
      row.status || "",
      row.comments || "",
      row.lookup_seconds || "",
      row.app_version || payload.app_version || "",
      row.source_url || "",
      now
    ]);

    sheet.insertRowsAfter(1, values.length);
    sheet.getRange(2, 1, values.length, HEADERS.length).setValues(values);
    return jsonResponse({ ok: true, appended: values.length });
  } catch (err) {
    return jsonResponse({ ok: false, error: String(err) }, 500);
  }
}

function getLeadSheet_() {
  const spreadsheet = SpreadsheetApp.openById(SPREADSHEET_ID);
  let sheet = spreadsheet.getSheetByName(SHEET_NAME);
  if (!sheet) {
    sheet = spreadsheet.insertSheet(SHEET_NAME);
  }

  const currentHeaders = sheet.getRange(1, 1, 1, HEADERS.length).getValues()[0];
  const needsHeaders = currentHeaders.join("") === "" || currentHeaders.join("|") !== HEADERS.join("|");
  if (needsHeaders) {
    sheet.getRange(1, 1, 1, HEADERS.length).setValues([HEADERS]);
    sheet.setFrozenRows(1);
    sheet.getRange(1, 1, 1, HEADERS.length).setFontWeight("bold");
    sheet.autoResizeColumns(1, HEADERS.length);
  }
  return sheet;
}

function jsonResponse(body, statusCode) {
  return ContentService
    .createTextOutput(JSON.stringify(body))
    .setMimeType(ContentService.MimeType.JSON);
}
