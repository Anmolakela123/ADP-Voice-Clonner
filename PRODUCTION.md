# Production checklist
- Use HTTPS and a real domain.
- Restrict CORS if exposing the API separately.
- Add authentication/rate limits before public launch.
- Monitor GPU RAM, disk usage and generation queue.
- Keep generated audio and uploaded references on persistent storage with cleanup.
- Back up configuration, not model cache if storage is constrained.
