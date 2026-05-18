 export const getTimeRatio = () => {
   return (new Date().getHours() * 60 + new Date().getMinutes()) / (24 * 60);
 };

 export const getSunAngle = (timeRatio) => {
   let angle;
   if (timeRatio >= 0.25 && timeRatio <= 0.75) {
     // Day: upper half, -90° to 90°
     angle = ((timeRatio - 0.25) / 0.5) * Math.PI - Math.PI / 2;
   } else {
     // Night: bottom half, 90° to 270°
     if (timeRatio < 0.25) {
       angle = (timeRatio / 0.25) * Math.PI + Math.PI / 2;
     } else {
       angle = ((timeRatio - 0.75) / 0.25) * Math.PI + Math.PI / 2;
     }
   }
   return angle;
 };

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

export const formatTimeWithTimezone = (isoString, timezone) => {
    if (!isoString) return 'N/A';
    if (timezone === undefined || timezone === null) {
      return formatLocalTime(isoString);
    }
    try {
      const date = new Date(isoString);
      if (typeof timezone === 'string') {
        return date.toLocaleTimeString('en-US', {
          timeZone: timezone,
          hour12: false,
          hour: '2-digit',
          minute: '2-digit'
        });
      }
      const utcTime = date.getTime() + (date.getTimezoneOffset() * 60000);
      const targetTime = new Date(utcTime + (timezone * 1000));
      return targetTime.toLocaleTimeString('en-US', {
        hour12: false,
        hour: '2-digit',
        minute: '2-digit'
      });
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
