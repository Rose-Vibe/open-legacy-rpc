import { createSocket } from 'node:dgram';
import type { Socket, RemoteInfo } from 'node:dgram';
import type { AddressInfo } from './types.js';

export type MessageHandler = (data: Uint8Array, remote: AddressInfo) => void;
export type ErrorHandler = (err: Error) => void;

export class UdpSocket {
  private socket: Socket | null = null;
  private messageHandlers: MessageHandler[] = [];
  private errorHandler: ErrorHandler | null = null;

  bind(port: number, address = '0.0.0.0'): Promise<void> {
    return new Promise((resolve, reject) => {
      const sock = createSocket('udp4');
      sock.on('message', (msg: Buffer, rinfo: RemoteInfo) => {
        const data = new Uint8Array(msg);
        const remote = { host: rinfo.address, port: rinfo.port };
        for (const handler of this.messageHandlers) {
          try {
            handler(data, remote);
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

  /** Set a single exclusive handler, replacing any previously set via onMessage (not addMessageHandler). */
  onMessage(handler: MessageHandler): void {
    // Replace only the first slot (index 0); preserve any addMessageHandler slots beyond that.
    if (this.messageHandlers.length === 0) {
      this.messageHandlers.push(handler);
    } else {
      this.messageHandlers[0] = handler;
    }
  }

  /** Add a handler alongside existing ones. Returns an unsubscribe function. */
  addMessageHandler(handler: MessageHandler): () => void {
    this.messageHandlers.push(handler);
    return () => {
      const idx = this.messageHandlers.indexOf(handler);
      if (idx >= 0) this.messageHandlers.splice(idx, 1);
    };
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
