# admin_activeAD

## Deployment in Docker

```bash
docker compose build
docker compose up -d
```

## Manual run

Start the bot directly without Docker:

```bash
python -m bot.main
```

If you run the container manually and override the default command, use the same module form:

```bash
docker run <image> python -m bot.main
```
