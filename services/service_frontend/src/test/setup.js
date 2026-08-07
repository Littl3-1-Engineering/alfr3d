import '@testing-library/jest-dom'

if (typeof Element !== 'undefined' && !Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = function () {}
}

if (typeof document !== 'undefined' && !document.getElementById('root')) {
  const root = document.createElement('div')
  root.id = 'root'
  document.body.appendChild(root)
}

HTMLCanvasElement.prototype.getContext = function () {
  return {
      fillStyle: '',
      strokeStyle: '',
      lineWidth: 1,
      globalAlpha: 1,
      font: '',
      textAlign: '',
      beginPath: () => {},
      closePath: () => {},
      moveTo: () => {},
      lineTo: () => {},
      arc: () => {},
      rect: () => {},
      fill: () => {},
      stroke: () => {},
      fillRect: () => {},
      strokeRect: () => {},
      clearRect: () => {},
      save: () => {},
      restore: () => {},
      translate: () => {},
      scale: () => {},
      rotate: () => {},
      setTransform: () => {},
      clip: () => {},
      createLinearGradient: () => ({ addColorStop: () => {} }),
      createRadialGradient: () => ({ addColorStop: () => {} }),
      drawImage: () => {},
      getImageData: () => ({ data: [] }),
      putImageData: () => {},
      measureText: () => ({ width: 0 }),
    }
  }

if (typeof window !== 'undefined' && !window.WebSocket) {
  class MockWebSocket {
    static OPEN = 1
    static CONNECTING = 0
    readyState = 1
    constructor() {}
    send() {}
    close() {}
  }
  window.WebSocket = MockWebSocket
}
