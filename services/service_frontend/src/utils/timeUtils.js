 export const getTimeRatio = () => {
   return (new Date().getHours() * 60 + new Date().getMinutes()) / (24 * 60);
 };

 // Maps a sky position onto the Core HUD orbit arc: eastern horizon -> 9 o'clock (left),
 // zenith -> 12 o'clock, western horizon -> 3 o'clock (right). Objects below the horizon
 // continue around the lower arc and are dimmed by the UI.
 export const getAngleFromSky = (altitudeDeg, azimuthDeg) => {
   const elevation = (altitudeDeg * Math.PI) / 180;
   return azimuthDeg <= 180 ? -Math.PI + elevation : -elevation;
 };

 export const getSunAngle = (date, lat, lon) => getAngleFromSky(getSunAltitude(date, lat, lon), getSunAzimuth(date, lat, lon));

 export const getMoonAngle = (date, lat, lon) => getAngleFromSky(getMoonAltitude(date, lat, lon), getMoonAzimuth(date, lat, lon));

 export const getSunAzimuth = (date, lat, lon) => getAzimuth(date, lat, lon, false);

 export const getMoonAzimuth = (date, lat, lon) => getAzimuth(date, lat, lon, true);

 // Meeus azimuth: compass bearing in degrees clockwise from North.
 const getAzimuth = (date, lat, lon, moon) => {
   const d = toJulianDate(date) - 2451545.0;
   let lambdaRad;
   if (moon) {
     const L = rad(218.316 + 13.176396 * d);
     const M = rad(134.963 + 13.064993 * d);
     const F = rad(93.272 + 13.229350 * d);
     const D = rad(297.850 + 12.190749 * d);
     lambdaRad = L
       + rad(6.289) * Math.sin(M)
       + rad(1.274) * Math.sin(2 * D - M)
       + rad(0.658) * Math.sin(2 * D)
       + rad(0.214) * Math.sin(2 * M)
       - rad(0.114) * Math.sin(F);
   } else {
     const meanAnomaly = 357.5291 + 0.98560028 * d;
     const meanLongitude = 280.459 + 0.98564736 * d;
     const trueLongitude = meanLongitude
       + 1.915 * Math.sin(rad(meanAnomaly))
       + 0.020 * Math.sin(rad(2 * meanAnomaly));
     lambdaRad = rad(trueLongitude);
   }
   const obliquity = 23.439 - 0.0000004 * d;
   const ra = Math.atan2(Math.cos(rad(obliquity)) * Math.sin(lambdaRad), Math.cos(lambdaRad));
   const dec = Math.asin(Math.sin(rad(obliquity)) * Math.sin(lambdaRad));
   const hourAngle = rad(getGMSTDegrees(date) + lon) - ra;
   const azFromSouth = Math.atan2(
     Math.sin(hourAngle),
     Math.cos(hourAngle) * Math.sin(rad(lat)) - Math.tan(dec) * Math.cos(rad(lat))
   );
   return (deg(azFromSouth) + 180) % 360;
 };

 const rad = (deg) => (deg * Math.PI) / 180;
 const deg = (rad) => (rad * 180) / Math.PI;

 // Julian date (days since 4713 BC, 12:00 UT)
 export const toJulianDate = (date) => date.getTime() / 86400000 + 2440587.5;

 // Greenwich Mean Sidereal Time in degrees
 export const getGMSTDegrees = (date) => {
   const d = toJulianDate(date) - 2451545.0;
   return ((280.46061837 + 360.98564736629 * d) % 360 + 360) % 360;
 };

 // Meeus solar position: apparent altitude above the horizon in degrees.
 export const getSunAltitude = (date, lat, lon) => {
   const d = toJulianDate(date) - 2451545.0;
   const meanAnomaly = 357.5291 + 0.98560028 * d;
   const meanLongitude = 280.459 + 0.98564736 * d;
   const trueLongitude = meanLongitude
     + 1.915 * Math.sin(rad(meanAnomaly))
     + 0.020 * Math.sin(rad(2 * meanAnomaly));
   const obliquity = 23.439 - 0.0000004 * d;
   const l = rad(trueLongitude);
   const ra = Math.atan2(Math.cos(rad(obliquity)) * Math.sin(l), Math.cos(l));
   const dec = Math.asin(Math.sin(rad(obliquity)) * Math.sin(l));
   const hourAngle = rad(getGMSTDegrees(date) + lon) - ra;
   return deg(
     Math.asin(
       Math.sin(rad(lat)) * Math.sin(dec)
       + Math.cos(rad(lat)) * Math.cos(dec) * Math.cos(hourAngle)
     )
   );
 };

  // Meeus low-precision lunar position: apparent altitude in degrees.
  export const getMoonAltitude = (date, lat, lon) => {
    const d = toJulianDate(date) - 2451545.0;
    const L = rad(218.316 + 13.176396 * d);          // mean longitude
    const M = rad(134.963 + 13.064993 * d);          // mean anomaly
    const F = rad(93.272 + 13.229350 * d);           // argument of latitude
    const D = rad(297.850 + 12.190749 * d);          // sun mean elongation
    const lambda = L
      + rad(6.289) * Math.sin(M)
      + rad(1.274) * Math.sin(2 * D - M)
      + rad(0.658) * Math.sin(2 * D)
      + rad(0.214) * Math.sin(2 * M)
      - rad(0.114) * Math.sin(F);
   const obliquity = 23.439 - 0.0000004 * d;
   const ra = Math.atan2(Math.cos(rad(obliquity)) * Math.sin(lambda), Math.cos(lambda));
   const dec = Math.asin(Math.sin(rad(obliquity)) * Math.sin(lambda));
   const hourAngle = rad(getGMSTDegrees(date) + lon) - ra;
   return deg(
     Math.asin(
       Math.sin(rad(lat)) * Math.sin(dec)
       + Math.cos(rad(lat)) * Math.cos(dec) * Math.cos(hourAngle)
     )
   );
 };

 // Clock ring: hour angle (radians) clockwise from 00:00 at the top.
 export const getClockAngle = (timeRatio) => timeRatio * 2 * Math.PI;

   export const formatLocalTime = (isoString) => {
     try {
       const date = new Date(isoString);
       return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });
     } catch (e) {
       // Fallback if not ISO
       return isoString;
     }
   };

export const formatCreatedDate = (dateString) => {
     if (!dateString) return 'UNKNOWN';
     const date = new Date(dateString);
     const day = String(date.getDate()).padStart(2, '0');
     const month = String(date.getMonth() + 1).padStart(2, '0');
     const year = date.getFullYear();
     return `D${day}M${month} Y${year}`;
   };

// True when the ISO string carries an explicit zone offset (e.g. "Z", "+04:00", "-04:00").
const _hasExplicitTz = (s) => /(?:Z|[+-]\d{2}:?\d{2})$/i.test(s.trim());

// Render a wall-clock "HH:MM" from an instant (ms) treated as if it were UTC.
const _formatWallClock = (ms) => new Date(ms).toISOString().slice(11, 16);

export const formatTimeWithTimezone = (isoString, timezone) => {
    if (!isoString) return 'N/A';
    if (timezone === undefined || timezone === null) {
      return formatLocalTime(isoString);
    }
    try {
      if (_hasExplicitTz(isoString)) {
        if (typeof timezone === 'string') {
          return new Date(isoString).toLocaleTimeString('en-US', {
            timeZone: timezone,
            hour12: false,
            hour: '2-digit',
            minute: '2-digit'
          });
        }
        // Absolute instant → shift into the location's local frame and render its wall clock.
        return _formatWallClock(new Date(isoString).getTime() + timezone * 1000);
      }
      // Naive string → stored as location-local wall clock; display it directly.
      const wall = new Date(isoString.replace(' ', 'T') + 'Z');
      if (Number.isNaN(wall.getTime())) return isoString;
      return _formatWallClock(wall.getTime());
    } catch (e) {
      return isoString;
    }
  };

export const getCurrentTimeWithTimezone = (timezone) => {
    if (timezone === undefined || timezone === null) {
      return new Date();
    }
    const now = new Date();
    if (typeof timezone === 'string') {
      try {
        return new Date(
          now.toLocaleString('en-US', { timeZone: timezone })
        );
      } catch (e) {
        return now;
      }
    }
    const utcTime = now.getTime() + (now.getTimezoneOffset() * 60000);
    return new Date(utcTime + (timezone * 1000));
  };

export const formatDateWithTimezone = (timezone) => {
    if (timezone === undefined || timezone === null) {
      return new Date().toLocaleDateString('en-US', {
        weekday: 'long',
        year: 'numeric',
        month: 'long',
        day: 'numeric'
      });
    }
    const date = getCurrentTimeWithTimezone(timezone);
    return date.toLocaleDateString('en-US', {
      weekday: 'long',
      year: 'numeric',
      month: 'long',
      day: 'numeric'
    });
  };
