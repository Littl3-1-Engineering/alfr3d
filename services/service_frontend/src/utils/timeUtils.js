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