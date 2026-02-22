# Online Users Detection Plan

1. Keep an in-memory presence map keyed by `userId` in the websocket layer.
2. On websocket `connect`, validate session and register the socket with `lastSeenAt`.
3. On websocket `disconnect`, remove socket membership and set offline only when no sockets remain.
4. Add a heartbeat packet from client every 30 seconds and refresh `lastSeenAt` on each heartbeat.
5. Expire stale users after a 90 second timeout to handle abrupt network loss.
6. Broadcast `presence:update` to each room when presence changes.
7. For multi-instance deployments, move presence state to Redis and sync events with pub/sub.
8. Expose a secure endpoint for current online members per room, filtered by membership.
