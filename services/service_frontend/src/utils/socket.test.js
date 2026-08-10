import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

class MockWebSocket {
  static CONNECTING = 0
  static OPEN = 1
  static CLOSING = 2
  static CLOSED = 3
  static instances = []

  constructor(url) {
    this.url = url
    this.readyState = MockWebSocket.OPEN
    this.onopen = null
    this.onclose = null
    this.onerror = null
    this.onmessage = null
    this.sent = []
    MockWebSocket.instances.push(this)
  }

  send(data) {
    this.sent.push(data)
  }

  close() {
    this.readyState = MockWebSocket.CLOSED
    if (this.onclose) this.onclose({ code: 1000 })
  }

  static emitOpen(ws) {
    ws.readyState = MockWebSocket.OPEN
    if (ws.onopen) ws.onopen({})
  }

  static emitMessage(ws, data) {
    if (ws.onmessage) ws.onmessage({ data })
  }
}

describe('socket client', () => {
  let socket

  async function loadSocket() {
    vi.resetModules()
    vi.stubGlobal('WebSocket', MockWebSocket)
    const mod = await import('./socket')
    return mod.socket
  }

  beforeEach(async () => {
    MockWebSocket.instances = []
    socket = await loadSocket()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.useRealTimers()
    socket.close()
  })

  it('connects to a ws:// endpoint derived from the base url', () => {
    socket.connect()
    expect(MockWebSocket.instances).toHaveLength(1)
    expect(MockWebSocket.instances[0].url).toBe('ws://localhost:3000/ws')
  })

  it('marks the client connected on open and resets reconnect attempts', () => {
    socket.connect()
    MockWebSocket.emitOpen(MockWebSocket.instances[0])
    expect(socket.isConnected).toBe(true)
    expect(socket.reconnectAttempts).toBe(0)
  })

  it('does not create a second socket when already open', () => {
    socket.connect()
    MockWebSocket.emitOpen(MockWebSocket.instances[0])
    socket.connect()
    expect(MockWebSocket.instances).toHaveLength(1)
  })

  it('dispatches parsed message data to listeners registered for that event', () => {
    const listener = vi.fn()
    socket.on('events', listener)
    socket.connect()
    MockWebSocket.emitMessage(MockWebSocket.instances[0], JSON.stringify({ event: 'events', data: { foo: 1 } }))
    expect(listener).toHaveBeenCalledWith({ foo: 1 })
  })

  it('ignores events with no listeners and malformed payloads', () => {
    const listener = vi.fn()
    socket.on('events', listener)
    socket.connect()
    const ws = MockWebSocket.instances[0]
    MockWebSocket.emitMessage(ws, JSON.stringify({ event: 'other', data: {} }))
    MockWebSocket.emitMessage(ws, 'not json')
    expect(listener).not.toHaveBeenCalled()
  })

  it('off removes a listener and the unsubscribe function works', () => {
    const listener = vi.fn()
    const unsubscribe = socket.on('events', listener)
    socket.connect()
    const ws = MockWebSocket.instances[0]
    MockWebSocket.emitMessage(ws, JSON.stringify({ event: 'events', data: 1 }))
    expect(listener).toHaveBeenCalledTimes(1)
    unsubscribe()
    MockWebSocket.emitMessage(ws, JSON.stringify({ event: 'events', data: 2 }))
    expect(listener).toHaveBeenCalledTimes(1)
    socket.off('events', listener)
  })

  it('emit serializes and sends when the socket is open', () => {
    socket.connect()
    MockWebSocket.emitOpen(MockWebSocket.instances[0])
    socket.emit('ping', { ts: 1 })
    expect(MockWebSocket.instances[0].sent).toEqual([JSON.stringify({ event: 'ping', data: { ts: 1 } })])
  })

  it('emit does nothing when the socket is closed', () => {
    socket.connect()
    const ws = MockWebSocket.instances[0]
    ws.close()
    socket.emit('ping', {})
    expect(ws.sent).toHaveLength(0)
  })

  it('reconnects on close up to maxReconnectAttempts', () => {
    vi.useFakeTimers()
    socket.connect()
    for (let i = 0; i < socket.maxReconnectAttempts + 1; i++) {
      const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1]
      ws.close()
      vi.advanceTimersByTime(socket.reconnectDelay)
    }
    // initial connection + one per reconnect attempt
    expect(MockWebSocket.instances).toHaveLength(socket.maxReconnectAttempts + 1)
    expect(socket.reconnectAttempts).toBe(socket.maxReconnectAttempts)
    // no further reconnect attempts once the max is reached
    vi.advanceTimersByTime(socket.reconnectDelay * 5)
    expect(MockWebSocket.instances).toHaveLength(socket.maxReconnectAttempts + 1)
  })

  it('close tears down the socket and clears connection state', () => {
    socket.connect()
    MockWebSocket.emitOpen(MockWebSocket.instances[0])
    socket.close()
    expect(MockWebSocket.instances[0].readyState).toBe(MockWebSocket.CLOSED)
    expect(socket.isConnected).toBe(false)
    expect(socket.socket).toBeNull()
  })
})
