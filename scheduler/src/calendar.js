/**
 * calendar.js
 * -----------
 * Business logic for querying available slots, booking, cancelling and
 * listing Google Calendar meetings.
 *
 * Environment variables consumed:
 *   CALENDAR_ID           — Google Calendar ID (required)
 *   SCHEDULER_TIMEZONE    — IANA tz for working hours (default: Asia/Jerusalem)
 *   WORKING_HOURS_START   — 24h HH:MM start of bookable day (default: 09:00)
 *   WORKING_HOURS_END     — 24h HH:MM end of bookable day   (default: 18:00)
 */

'use strict';

const { getCalendarClient } = require('./auth');
const { addMinutes, parseISO, isWithinInterval, format } = require('date-fns');
const { toZonedTime, fromZonedTime, formatInTimeZone } = require('date-fns-tz');

// ── Configuration ──────────────────────────────────────────────────────────────

const CALENDAR_ID = process.env.CALENDAR_ID;
const SCHEDULER_TIMEZONE = process.env.SCHEDULER_TIMEZONE || 'Asia/Jerusalem';
const WORKING_HOURS_START = process.env.WORKING_HOURS_START || '09:00';
const WORKING_HOURS_END = process.env.WORKING_HOURS_END || '18:00';

/** Slot granularity in minutes (calendar offers slots every 30 min). */
const SLOT_GRANULARITY_MINUTES = 30;

// ── Internal helpers ───────────────────────────────────────────────────────────

/**
 * Parse "HH:MM" into { hours, minutes }.
 * @param {string} hhmm
 * @returns {{ hours: number, minutes: number }}
 */
function parseHHMM(hhmm) {
  const [hours, minutes] = hhmm.split(':').map(Number);
  return { hours, minutes };
}

/**
 * Given a calendar Date object (in UTC) return the meet link from conferenceData.
 * @param {object} event  — raw Calendar API event resource
 * @returns {string|null}
 */
function extractMeetLink(event) {
  const ep = event.conferenceData?.entryPoints;
  if (!ep) return null;
  const video = ep.find((e) => e.entryPointType === 'video');
  return video ? video.uri : null;
}

/**
 * Check whether two intervals [startA, endA) and [startB, endB) overlap.
 * @param {Date} startA
 * @param {Date} endA
 * @param {Date} startB
 * @param {Date} endB
 * @returns {boolean}
 */
function intervalsOverlap(startA, endA, startB, endB) {
  return startA < endB && endA > startB;
}

// ── Exported functions ─────────────────────────────────────────────────────────

/**
 * getAvailableSlots
 * -----------------
 * Returns a list of free time slots for a given date.
 *
 * @param {string} dateStr        — Date in YYYY-MM-DD format (e.g. "2026-07-10")
 * @param {string} tz             — IANA timezone of the requesting user
 * @param {number} durationMinutes — Desired meeting duration in minutes
 * @returns {Promise<Array<{ startISO: string, endISO: string, displayTime: string }>>}
 */
async function getAvailableSlots(dateStr, tz, durationMinutes) {
  if (!CALENDAR_ID) {
    throw new Error('CALENDAR_ID environment variable is not set.');
  }

  const calendar = await getCalendarClient();
  const userTz = tz || SCHEDULER_TIMEZONE;

  // ── Build the working-hours window in UTC ────────────────────────────────────
  const { hours: startHour, minutes: startMin } = parseHHMM(WORKING_HOURS_START);
  const { hours: endHour, minutes: endMin } = parseHHMM(WORKING_HOURS_END);

  // Construct the start/end of the working day as zoned times, then convert to UTC.
  const dayStartLocal = new Date(`${dateStr}T${WORKING_HOURS_START}:00`);
  const dayEndLocal = new Date(`${dateStr}T${WORKING_HOURS_END}:00`);

  // fromZonedTime converts a local datetime in the given tz to a UTC Date.
  const dayStartUTC = fromZonedTime(
    new Date(
      parseInt(dateStr.slice(0, 4)),
      parseInt(dateStr.slice(5, 7)) - 1,
      parseInt(dateStr.slice(8, 10)),
      startHour,
      startMin,
      0,
      0
    ),
    SCHEDULER_TIMEZONE
  );
  const dayEndUTC = fromZonedTime(
    new Date(
      parseInt(dateStr.slice(0, 4)),
      parseInt(dateStr.slice(5, 7)) - 1,
      parseInt(dateStr.slice(8, 10)),
      endHour,
      endMin,
      0,
      0
    ),
    SCHEDULER_TIMEZONE
  );

  // ── Fetch existing events from Google Calendar ───────────────────────────────
  const response = await calendar.events.list({
    calendarId: CALENDAR_ID,
    timeMin: dayStartUTC.toISOString(),
    timeMax: dayEndUTC.toISOString(),
    singleEvents: true,
    orderBy: 'startTime',
  });

  const existingEvents = (response.data.items || []).filter(
    (ev) => ev.status !== 'cancelled'
  );

  // Parse existing events into { start: Date, end: Date } intervals.
  const busyIntervals = existingEvents.map((ev) => ({
    start: new Date(ev.start.dateTime || ev.start.date),
    end: new Date(ev.end.dateTime || ev.end.date),
  }));

  // ── Generate candidate slots ─────────────────────────────────────────────────
  const slots = [];
  let cursor = dayStartUTC;

  while (cursor < dayEndUTC) {
    const slotEnd = addMinutes(cursor, durationMinutes);

    // Don't offer a slot that extends beyond the working day.
    if (slotEnd > dayEndUTC) break;

    // Check for overlap with any existing event.
    const isBlocked = busyIntervals.some((busy) =>
      intervalsOverlap(cursor, slotEnd, busy.start, busy.end)
    );

    if (!isBlocked) {
      // Format display time in the user's requested timezone.
      const displayTime = formatInTimeZone(cursor, userTz, 'HH:mm zzz');

      slots.push({
        startISO: cursor.toISOString(),
        endISO: slotEnd.toISOString(),
        displayTime,
      });
    }

    cursor = addMinutes(cursor, SLOT_GRANULARITY_MINUTES);
  }

  return slots;
}

/**
 * bookMeeting
 * -----------
 * Creates a Google Calendar event with a Google Meet conference link.
 *
 * @param {{ name: string, email: string, subject: string, startISO: string, durationMinutes: number, userTz: string }} params
 * @returns {Promise<{ ok: boolean, eventId: string, meetLink: string|null }>}
 */
async function bookMeeting({ name, email, subject, startISO, durationMinutes, userTz }) {
  if (!CALENDAR_ID) {
    throw new Error('CALENDAR_ID environment variable is not set.');
  }

  const calendar = await getCalendarClient();

  const startDate = parseISO(startISO);
  const endDate = addMinutes(startDate, durationMinutes);
  const tz = userTz || SCHEDULER_TIMEZONE;

  // Build the event resource.
  const event = {
    summary: subject,
    description: `Booked by ${name} (${email}) via Change Navigator Scheduler.`,
    attendees: [{ email }],
    start: {
      dateTime: startDate.toISOString(),
      timeZone: tz,
    },
    end: {
      dateTime: endDate.toISOString(),
      timeZone: tz,
    },
    // Request Google to generate a Meet link.
    conferenceData: {
      createRequest: {
        requestId: `cn-${Date.now()}-${Math.random().toString(36).slice(2)}`,
        conferenceSolutionKey: { type: 'hangoutsMeet' },
      },
    },
    reminders: {
      useDefault: false,
      overrides: [
        { method: 'email', minutes: 24 * 60 }, // 24 hours before
        { method: 'popup', minutes: 15 },       // 15 minutes before
      ],
    },
  };

  const response = await calendar.events.insert({
    calendarId: CALENDAR_ID,
    resource: event,
    // conferenceDataVersion: 1 is required to generate a Meet link.
    conferenceDataVersion: 1,
    sendUpdates: 'all', // Send invite emails to attendees.
  });

  const createdEvent = response.data;
  const meetLink = extractMeetLink(createdEvent);

  console.log(
    `[calendar] Event created: ${createdEvent.id} for ${email} at ${startISO}`
  );

  return {
    ok: true,
    eventId: createdEvent.id,
    meetLink,
  };
}

/**
 * cancelMeeting
 * -------------
 * Deletes a calendar event by its ID.
 *
 * @param {string} eventId  — Google Calendar event ID
 * @param {string} [reason] — Optional reason string (logged only)
 * @returns {Promise<{ ok: boolean }>}
 */
async function cancelMeeting(eventId, reason) {
  if (!CALENDAR_ID) {
    throw new Error('CALENDAR_ID environment variable is not set.');
  }
  if (!eventId) {
    throw new Error('eventId is required to cancel a meeting.');
  }

  const calendar = await getCalendarClient();

  await calendar.events.delete({
    calendarId: CALENDAR_ID,
    eventId,
    sendUpdates: 'all', // Notify attendees of cancellation.
  });

  console.log(
    `[calendar] Event ${eventId} cancelled. Reason: ${reason || '(none provided)'}`
  );

  return { ok: true };
}

/**
 * getBookings
 * -----------
 * Lists upcoming calendar events where the given email address is an attendee.
 * Looks ahead up to 60 days from now.
 *
 * @param {string} email — Attendee email to filter by
 * @returns {Promise<Array<{ eventId: string, subject: string, startISO: string, endISO: string, meetLink: string|null }>>}
 */
async function getBookings(email) {
  if (!CALENDAR_ID) {
    throw new Error('CALENDAR_ID environment variable is not set.');
  }
  if (!email) {
    throw new Error('email query parameter is required.');
  }

  const calendar = await getCalendarClient();

  const now = new Date();
  const lookahead = addMinutes(now, 60 * 24 * 60); // 60 days ahead

  // The Calendar API doesn't support filtering by attendee email directly,
  // so we fetch all upcoming events and filter client-side.
  const response = await calendar.events.list({
    calendarId: CALENDAR_ID,
    timeMin: now.toISOString(),
    timeMax: lookahead.toISOString(),
    singleEvents: true,
    orderBy: 'startTime',
    // Return at most 250 events (API max per page); add pagination if needed.
    maxResults: 250,
  });

  const events = (response.data.items || []).filter((ev) => {
    if (ev.status === 'cancelled') return false;
    const attendees = ev.attendees || [];
    return attendees.some(
      (a) => a.email.toLowerCase() === email.toLowerCase()
    );
  });

  return events.map((ev) => ({
    eventId: ev.id,
    subject: ev.summary || '(No title)',
    startISO: ev.start.dateTime || ev.start.date,
    endISO: ev.end.dateTime || ev.end.date,
    meetLink: extractMeetLink(ev),
  }));
}

module.exports = { getAvailableSlots, bookMeeting, cancelMeeting, getBookings };
