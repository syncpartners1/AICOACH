/**
 * middleware.js
 * ------------
 * Express middleware for API key authentication.
 *
 * Usage:
 *   const { requireApiKey } = require('./middleware');
 *   app.use('/api', requireApiKey);
 */

'use strict';

/**
 * requireApiKey — Express middleware that validates the X-Api-Key header
 * against the SCHEDULER_API_KEY environment variable.
 *
 * Behaviour:
 *  - If SCHEDULER_API_KEY is not set, logs a warning and allows the request
 *    through (useful during local development without secrets configured).
 *  - If the header is missing or does not match, responds with HTTP 401.
 *  - If the header matches, calls next() to pass control to the route handler.
 *
 * @param {import('express').Request}  req
 * @param {import('express').Response} res
 * @param {import('express').NextFunction} next
 */
function requireApiKey(req, res, next) {
  const expectedKey = process.env.SCHEDULER_API_KEY;

  // ── Dev-mode bypass ─────────────────────────────────────────────────────────
  if (!expectedKey) {
    console.warn(
      '[WARN] SCHEDULER_API_KEY is not set — API key check is DISABLED. ' +
        'Set the variable before deploying to production.'
    );
    return next();
  }

  // ── Validate the header ──────────────────────────────────────────────────────
  const providedKey = req.headers['x-api-key'];

  if (!providedKey) {
    return res.status(401).json({
      ok: false,
      error: 'Missing X-Api-Key header.',
    });
  }

  if (providedKey !== expectedKey) {
    return res.status(401).json({
      ok: false,
      error: 'Invalid API key.',
    });
  }

  return next();
}

module.exports = { requireApiKey };
