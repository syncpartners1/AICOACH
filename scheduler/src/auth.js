/**
 * auth.js
 * -------
 * Google Calendar authentication via a GCP Service Account.
 *
 * The service account JSON is expected to be stored as a single-line JSON
 * string in the GOOGLE_SERVICE_ACCOUNT_JSON environment variable (injected
 * from Secret Manager on Cloud Run).
 */

'use strict';

const { google } = require('googleapis');

// Cache the authenticated client so we don't re-parse credentials on every call.
let _calendarClient = null;

/**
 * getCalendarClient
 * -----------------
 * Returns an authenticated Google Calendar v3 client, creating it on first
 * call and returning the cached instance on subsequent calls.
 *
 * @returns {Promise<import('googleapis').calendar_v3.Calendar>}
 * @throws  {Error} when GOOGLE_SERVICE_ACCOUNT_JSON is not set or is invalid.
 */
async function getCalendarClient() {
  if (_calendarClient) {
    return _calendarClient;
  }

  const saJsonRaw = process.env.GOOGLE_SERVICE_ACCOUNT_JSON;
  if (!saJsonRaw) {
    throw new Error(
      'GOOGLE_SERVICE_ACCOUNT_JSON environment variable is not set. ' +
        'Provide the service account key JSON as a single-line string ' +
        '(or mount it via Secret Manager on Cloud Run).'
    );
  }

  let credentials;
  try {
    credentials = JSON.parse(saJsonRaw);
  } catch (parseErr) {
    throw new Error(
      `Failed to parse GOOGLE_SERVICE_ACCOUNT_JSON: ${parseErr.message}. ` +
        'Make sure the value is valid JSON (no line breaks, properly escaped).'
    );
  }

  // Build a GoogleAuth client scoped to Calendar read/write.
  const auth = new google.auth.GoogleAuth({
    credentials,
    scopes: ['https://www.googleapis.com/auth/calendar'],
  });

  _calendarClient = google.calendar({ version: 'v3', auth });
  console.log('[auth] Google Calendar client initialised successfully.');
  return _calendarClient;
}

/**
 * resetCalendarClient (test helper)
 * ----------------------------------
 * Clears the cached client so tests can inject a fresh environment.
 */
function resetCalendarClient() {
  _calendarClient = null;
}

module.exports = { getCalendarClient, resetCalendarClient };
