import { createSocket } from 'node:dgram';
import type { Socket, RemoteInfo } from 'node:dgram';
import type { AddressInfo } from './types.js';

export type MessageHandler = (data: Uint8Array, remote: AddressInfo) => void;
export type ErrorHandler = (err: Error) => void;

export class UdpSocket {
  private socket: Socket | null = null;
  private messageHandler: MessageHandler | null = null;
  private errorHandler: ErrorHandler | null = null;

  bind(port: number, address = '0.0.0.0'): Promise<void> {
    return new Promise((resolve, reject) => {
      const sock = createSocket('udp4');
      sock.on('message', (msg: Buffer, rinfo: RemoteInfo) => {
        if (this.messageHandler) {
          try {
            this.messageHandler(new Uint8Array(msg), { host: rinfo.address, port: rinfo.port });
          } catch (err) {
            if (this.errorHandler) {
              this.errorHandler(err instanceof Error ? err : new Error(String(err)));
            } else {
              console.error('[UdpSocket] unhandled error in message handler:', err); // eslint-disable-line no-console
            }
          }
        }
      });
      sock.on('error', reject);
      sock.bind(port, address, () => {
        sock.removeListener('error', reject);
        sock.on('error', (err: Error) => {
          if (this.errorHandler) {
            this.errorHandler(err);
          } else {
            console.error('[UdpSocket] socket error:', err); // eslint-disable-line no-console
          }
        });
        this.socket = sock;
        resolve();
      });
    });
  }

  onError(handler: ErrorHandler): void {
    this.errorHandler = handler;
  }

  sendTo(data: Uint8Array, host: string, port: number): void {
    this.socket?.send(data, 0, data.length, port, host);
  }

  onMessage(handler: MessageHandler): void {
    this.messageHandler = handler;
  }

  close(): Promise<void> {
    return new Promise((resolve) => {
      if (this.socket) {
        this.socket.close(() => {
          this.socket = null;
          resolve();
        });
      } else {
        resolve();
      }
    });
  }

  get localPort(): number | undefined {
    try {
      return this.socket?.address().port;
    } catch {
      return undefined;
    }
  }
}
