export const APP_TIMEZONE = "Asia/Kolkata";

const DATE_TIME_FORMATTER = new Intl.DateTimeFormat("en-IN", {
  timeZone: APP_TIMEZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: true,
});

const DATE_FORMATTER = new Intl.DateTimeFormat("en-CA", {
  timeZone: APP_TIMEZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

const TIME_FORMATTER = new Intl.DateTimeFormat("en-IN", {
  timeZone: APP_TIMEZONE,
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: true,
});

function parseValue(value) {
  if (!value) {
    return null;
  }

  const parsed = value instanceof Date ? value : new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function formatParts(formatter, value, fallback = "-") {
  const parsed = parseValue(value);
  if (!parsed) {
    return value ? String(value) : fallback;
  }
  return formatter.format(parsed);
}

export function formatDateTimeInAppTimezone(value, fallback = "-") {
  return formatParts(DATE_TIME_FORMATTER, value, fallback);
}

export function formatTimeInAppTimezone(value, fallback = "-") {
  return formatParts(TIME_FORMATTER, value, fallback);
}

export function formatDateInAppTimezone(value, fallback = "-") {
  return formatParts(DATE_FORMATTER, value, fallback);
}

export function getAppNow() {
  const now = new Date();
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: APP_TIMEZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  }).formatToParts(now);

  const lookup = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return new Date(`${lookup.year}-${lookup.month}-${lookup.day}T${lookup.hour}:${lookup.minute}:${lookup.second}`);
}

export function toDateInputValueInAppTimezone(value = getAppNow()) {
  return formatDateInAppTimezone(value);
}
