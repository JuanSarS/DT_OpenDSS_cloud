# Secretos locales

Genera los secretos y usuarios locales desde la raíz del repositorio:

```powershell
python scripts\init_local_secrets.py
```

El directorio `secrets/local/` contiene secretos de desarrollo y no debe
versionarse ni copiarse a las imágenes Docker.
