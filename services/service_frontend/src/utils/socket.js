import { io } from 'socket.io-client';
import { WS_BASE_URL } from '../config';

export const socket = io(WS_BASE_URL, {
  path: '/ws/socket.io',
  transports: ['websocket', 'polling'],
  reconnection: true,
  reconnectionAttempts: 5,
  reconnectionDelay: 1000,
});

export default socket;
