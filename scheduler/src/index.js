/**
 * index.js
 * --------
 * Entry point for the Change Navigator Scheduler microservice.
 *
 * Exposes:
 *   GET  /health          — liveness probe (no auth)
 *   GET  /api/slots       — available booking slots for a date
 *   POST /api/book        — create a calendar booking
 *   POST /api/cancel      — cancel a booking by eventId
 *   GET  /api/bookings    — list upcoming bookings for an email
 */

'use strict';

// Load .env variables before anything else (no-op in Cloud Run where env vars
// are injected by the runtime / Secret Manager).
require('dotenv').config();

const express = require('express');
const { requireApiKey } = require('./middleware');
const {
  getAvailableSlots,
  bookMeeting,
  cancelMeeting,
  getBookings,
} = require('./calendar');

const app = express();

// ── Global middleware ──────────────────────────────────────────────────────────

// Parse JSON request bodies.
app.use(express.json());

/**
 * Request logging middleware.
 * Logs: timestamp | method | path | status | duration (ms)
 */
app.use((req, res, next) => {
  const startedAt = Date.now();

  res.on('finish', () => {
    const duration = Date.now() - startedAt;
    console.log(
      `[${new Date().toISOString()}] ${req.method} ${req.path} → ${res.statusCode} (${duration}ms)`
    );
  });

  next();
});

// ── Routes ─────────────────────────────────────────────────────────────────────

/**
 * GET /health
 * -----------
 * Liveness / readiness probe used by Cloud Run.
 * No authentication required.
 */
app.get('/health', (_req, res) => {
  res.json({
    ok: true,
    service: 'change-navigator-scheduler',
    timestamp: new Date().toISOString(),
  });
});

/**
 * GET /api/slots
 * --------------
 * Returns available booking slots for a given date.
 *
 * Query params:
 *   date     {string}  YYYY-MM-DD  (required)
 *   tz       {string}  IANA timezone of the user (optional, defaults to SCHEDULER_TIMEZONE)
 *   duration {number}  Meeting duration in minutes (optional, default 60)
 *
 * Response:
 *   { ok: true, slots: [{ startISO, endISO, displayTime }] }
 */
app.get('/api/slots', requireApiKey, async (req, res, next) => {
  try {
    const { date, tz, duration = '60' } = req.query;

    if (typeof date !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(date)) {
      return res.status(400).json({
        ok: false,
        error: 'Query param "date" is required and must be a string in YYYY-MM-DD format.',
      });
    }

    if (tz !== undefined && typeof tz !== 'string') {
      return res.status(400).json({
        ok: false,
        error: 'Query param "tz" must be a string when provided.',
      });
    }

    if (typeof duration !== 'string') {
      return res.status(400).json({
        ok: false,
        error: 'Query param "duration" must be a positive integer (minutes).',
      });
    }

    if (tz !== undefined && typeof tz !== 'string') {
      return res.status(400).json({
        ok: false,
        error: 'Query param "tz" must be a valid IANA timezone string.',
      });
    }

    if (typeof duration !== 'string') {
      return res.status(400).json({
        ok: false,
        error: 'Query param "duration" must be a positive integer (minutes).',
      });
    }

    const durationMinutes = parseInt(duration, 10);
    if (isNaN(durationMinutes) || durationMinutes <= 0) {
      return res.status(400).json({
        ok: false,
        error: 'Query param "duration" must be a positive integer (minutes).',
      });
    }

    const slots = await getAvailableSlots(date, tz, durationMinutes);
    return res.json({ ok: true, slots });
  } catch (err) {
    return next(err);
  }
});

/**
 * POST /api/book
 * --------------
 * Creates a Google Calendar event with a Google Meet link.
 *
 * Body (JSON):
 *   name            {string}  Attendee's full name (required)
 *   email           {string}  Attendee's email     (required)
 *   subject         {string}  Meeting title        (required)
 *   startISO        {string}  ISO 8601 datetime    (required)
 *   durationMinutes {number}  Duration in minutes  (optional, default 60)
 *   userTz          {string}  IANA timezone        (optional)
 *
 * Response:
 *   { ok: true, eventId, meetLink }
 */
app.post('/api/book', requireApiKey, async (req, res, next) => {
  try {
    const {
      name,
      email,
      subject,
      startISO,
      durationMinutes = 60,
      userTz,
    } = req.body;

    // Basic validation.
    const missing = ['name', 'email', 'subject', 'startISO'].filter(
      (f) => !req.body[f]
    );
    if (missing.length > 0) {
      return res.status(400).json({
        ok: false,
        error: `Missing required body fields: ${missing.join(', ')}.`,
      });
    }

    // Validate email format lightly.
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      return res.status(400).json({ ok: false, error: 'Invalid email address.' });
    }

    const result = await bookMeeting({
      name,
      email,
      subject,
      startISO,
      durationMinutes: parseInt(durationMinutes, 10),
      userTz,
    });

    return res.json(result);
  } catch (err) {
    return next(err);
  }
});

/**
 * POST /api/cancel
 * ----------------
 * Cancels (deletes) a Google Calendar event.
 *
 * Body (JSON):
 *   eventId {string}  Google Calendar event ID (required)
 *   reason  {string}  Cancellation reason      (optional)
 *
 * Response:
 *   { ok: true }
 */
app.post('/api/cancel', requireApiKey, async (req, res, next) => {
  try {
    const { eventId, reason } = req.body;

    if (!eventId) {
      return res.status(400).json({
        ok: false,
        error: 'Body field "eventId" is required.',
      });
    }

    const result = await cancelMeeting(eventId, reason);
    return res.json(result);
  } catch (err) {
    return next(err);
  }
});

/**
 * GET /api/bookings
 * -----------------
 * Lists upcoming Google Calendar events for which the given email is an attendee.
 *
 * Query params:
 *   email {string}  Attendee email address (required)
 *
 * Response:
 *   { ok: true, bookings: [{ eventId, subject, startISO, endISO, meetLink }] }
 */
app.get('/api/bookings', requireApiKey, async (req, res, next) => {
  try {
    const { email } = req.query;

    if (!email) {
      return res.status(400).json({
        ok: false,
        error: 'Query param "email" is required.',
      });
    }

    const bookings = await getBookings(email);
    return res.json({ ok: true, bookings });
  } catch (err) {
    return next(err);
  }
});

// ── Global error handler ───────────────────────────────────────────────────────

/**
 * Catches any error thrown (or passed via next(err)) from route handlers and
 * returns a consistent JSON error response.
 *
 * Note: Express requires exactly 4 parameters for error-handling middleware.
 */
// eslint-disable-next-line no-unused-vars
app.use((err, _req, res, _next) => {
  // Log the full error server-side for debugging.
  console.error('[ERROR]', err.stack || err.message || err);

  // Surface a safe message to the client.
  const statusCode = err.statusCode || err.status || 500;
  return res.status(statusCode).json({
    ok: false,
    error: err.message || 'An unexpected error occurred.',
  });
});

// ── Start server ───────────────────────────────────────────────────────────────

const port = parseInt(process.env.PORT || '8080', 10);

app.listen(port, () => {
  console.log(
    `Change Navigator Scheduler running on port ${port} [env: ${process.env.NODE_ENV || 'development'}]`
  );
});

// Export for testing.
module.exports = app;
